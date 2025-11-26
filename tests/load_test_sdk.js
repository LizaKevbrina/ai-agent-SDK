/**
 * Load Testing for AI Agent SDK
 * 
 * Тестирование производительности под нагрузкой
 * Замена устаревшего tests/load_test.js (который был для микросервисов)
 * 
 * Запуск:
 *   k6 run tests/load_test_sdk.js --out json=load_test_results.json
 * 
 * Окружение:
 *   export AGENT_URL=http://localhost:8000
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';

// ========================================
// CUSTOM METRICS
// ========================================

const errorRate = new Rate('errors');
const agentDuration = new Trend('agent_duration');
const toolsUsed = new Counter('tools_used_total');
const contextUsed = new Rate('context_used_rate');
const tokensUsed = new Trend('tokens_used');

// ========================================
// TEST CONFIGURATION
// ========================================

export let options = {
  stages: [
    // Warm-up
    { duration: '1m', target: 10 },   // 0 → 10 users (1 min)
    
    // Normal load
    { duration: '1m', target: 50 },   // 10 → 50 users (1 min)
    { duration: '3m', target: 50 },   // Stay at 50 users (3 min)
    
    // Stress test
    { duration: '1m', target: 100 },  // 50 → 100 users (1 min)
    { duration: '2m', target: 100 },  // Stay at 100 users (2 min)
    
    // Spike test
    { duration: '30s', target: 200 }, // 100 → 200 users (spike!)
    { duration: '1m', target: 200 },  // Stay at 200 (1 min)
    
    // Cool-down
    { duration: '1m', target: 0 },    // 200 → 0 users
  ],
  
  thresholds: {
    // 95% запросов должны быть < 3 секунд
    'http_req_duration': ['p(95)<3000'],
    
    // Менее 5% ошибок
    'http_req_failed': ['rate<0.05'],
    
    // Средняя длительность агента < 2.5 сек
    'agent_duration': ['p(95)<2500'],
    
    // Частота ошибок < 5%
    'errors': ['rate<0.05'],
  },
  
  // Прерывание при критических ошибках
  abortOnFail: false,
  
  // Теги для фильтрации результатов
  tags: {
    test_type: 'load',
    environment: 'testing',
  },
};

// ========================================
// TEST DATA
// ========================================

const TEST_QUESTIONS = [
  // Real estate questions (should trigger RAG)
  'Какие квартиры есть в ЖК Солнечный?',
  'Покажи 2-комнатные квартиры до 6 миллионов',
  'Какие районы самые дорогие?',
  'Расскажи про ЖК на Приморском проспекте',
  'Что есть в продаже с хорошей планировкой?',
  
  // Calculation questions (should trigger calculate_mortgage)
  'Посчитай ипотеку на квартиру за 5 миллионов',
  'Какой будет платёж при ставке 12%?',
  'Сколько стоит ипотека на 30 лет?',
  
  // General questions (no RAG)
  'Привет!',
  'Что ты умеешь?',
  'Как дела?',
  'Расскажи о себе',
];

const BASE_URL = __ENV.AGENT_URL || 'http://localhost:8000';

// ========================================
// TEST SCENARIOS
// ========================================

export default function () {
  const sessionId = `load_test_${__VU}_${__ITER}`;
  const correlationId = `load-${Date.now()}-${sessionId}`;
  
  group('Full Agent Pipeline', function () {
    // Выбираем случайный вопрос
    const question = TEST_QUESTIONS[Math.floor(Math.random() * TEST_QUESTIONS.length)];
    
    const payload = JSON.stringify({
      message: question,
      session_id: sessionId,
      prompt_version: 'v1',
      input_type: 'text',
      use_openai: false,  // Use YandexGPT
    });
    
    const params = {
      headers: {
        'Content-Type': 'application/json',
        'X-Correlation-ID': correlationId,
      },
      timeout: '30s',
    };
    
    // ========================================
    // MAIN REQUEST
    // ========================================
    
    const startTime = new Date().getTime();
    const response = http.post(`${BASE_URL}/chat`, payload, params);
    const duration = new Date().getTime() - startTime;
    
    // Track custom metrics
    agentDuration.add(duration);
    
    // ========================================
    // CHECKS
    // ========================================
    
    const checkResult = check(response, {
      'status is 200': (r) => r.status === 200,
      'response has text': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.response && body.response.length > 0;
        } catch (e) {
          return false;
        }
      },
      'response time < 5s': (r) => r.timings.duration < 5000,
      'has correlation ID': (r) => r.headers['X-Correlation-Id'] !== undefined,
    });
    
    // Track errors
    if (!checkResult) {
      errorRate.add(1);
      console.error(
        `❌ Request failed: VU=${__VU}, Iter=${__ITER}, ` +
        `Status=${response.status}, Duration=${duration}ms`
      );
    } else {
      errorRate.add(0);
      
      // Parse response для дополнительных метрик
      try {
        const body = JSON.parse(response.body);
        
        // Track tool usage
        if (body.tools_used && body.tools_used.length > 0) {
          toolsUsed.add(body.tools_used.length);
          
          body.tools_used.forEach(tool => {
            console.log(`🔧 Tool used: ${tool}`);
          });
        }
        
        // Track context usage (RAG)
        if (body.context_used) {
          contextUsed.add(1);
          console.log(`📚 RAG context used: ${body.documents_found} documents`);
        } else {
          contextUsed.add(0);
        }
        
        // Track tokens
        if (body.tokens_used) {
          tokensUsed.add(body.tokens_used);
        }
        
        // Log successful request
        console.log(
          `✅ Request successful: VU=${__VU}, Iter=${__ITER}, ` +
          `Duration=${duration}ms, Tokens=${body.tokens_used}, ` +
          `Tools=${body.tools_used.join(',') || 'none'}`
        );
        
      } catch (e) {
        console.warn(`⚠️ Failed to parse response body: ${e}`);
      }
    }
  });
  
  // ========================================
  // THINK TIME (между запросами)
  // ========================================
  
  // Реалистичная задержка: 1-4 секунды между сообщениями
  sleep(Math.random() * 3 + 1);
}

// ========================================
// SETUP / TEARDOWN
// ========================================

export function setup() {
  console.log('🚀 Starting load test...');
  console.log(`   Base URL: ${BASE_URL}`);
  console.log(`   Test questions: ${TEST_QUESTIONS.length}`);
  
  // Health check перед тестом
  const healthResponse = http.get(`${BASE_URL}/health`, { timeout: '10s' });
  
  if (healthResponse.status !== 200) {
    console.error('❌ Health check failed! Aborting test.');
    throw new Error('Agent is not healthy');
  }
  
  console.log('✅ Health check passed');
  
  return { baseUrl: BASE_URL };
}

export function teardown(data) {
  console.log('🏁 Load test completed');
  console.log(`   Base URL: ${data.baseUrl}`);
}

// ========================================
// SUMMARY HANDLER
// ========================================

export function handleSummary(data) {
  console.log('\n📊 === LOAD TEST SUMMARY ===\n');
  
  // Извлечение метрик
  const metrics = data.metrics;
  
  console.log('HTTP Requests:');
  console.log(`  Total: ${metrics.http_reqs.values.count}`);
  console.log(`  Failed: ${metrics.http_req_failed.values.rate * 100}%`);
  console.log(`  Duration (p95): ${metrics.http_req_duration.values['p(95)']}ms`);
  
  console.log('\nAgent Performance:');
  console.log(`  Duration (avg): ${metrics.agent_duration.values.avg}ms`);
  console.log(`  Duration (p95): ${metrics.agent_duration.values['p(95)']}ms`);
  console.log(`  Error rate: ${metrics.errors.values.rate * 100}%`);
  
  console.log('\nRAG Usage:');
  console.log(`  Context used: ${metrics.context_used_rate.values.rate * 100}%`);
  console.log(`  Tools used: ${metrics.tools_used_total.values.count}`);
  
  console.log('\nTokens:');
  console.log(`  Avg tokens/request: ${metrics.tokens_used.values.avg}`);
  console.log(`  Total tokens: ${metrics.tokens_used.values.count}`);
  
  // Threshold violations
  const thresholds = data.root_group.checks;
  const failedThresholds = Object.keys(thresholds).filter(
    key => thresholds[key].fails > 0
  );
  
  if (failedThresholds.length > 0) {
    console.log('\n⚠️  Failed Thresholds:');
    failedThresholds.forEach(threshold => {
      console.log(`  - ${threshold}: ${thresholds[threshold].fails} failures`);
    });
  } else {
    console.log('\n✅ All thresholds passed!');
  }
  
  console.log('\n============================\n');
  
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'load_test_results.json': JSON.stringify(data, null, 2),
  };
}
