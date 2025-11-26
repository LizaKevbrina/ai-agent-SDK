"""
Security Tools
Migrated from: services/validation/main.py
Provides: Input validation, SQL injection prevention, XSS filtering
UPDATED: Added Prometheus metrics
"""

from langchain.tools import tool
from typing import Optional
import re
import logging
from prometheus_client import Counter

logger = logging.getLogger(__name__)

# ========================================
# PROMETHEUS METRICS
# ========================================

security_validation_total = Counter(
    'security_validation_total',
    'Total security validations',
    ['status']  # passed, blocked
)

security_threats_detected = Counter(
    'security_threats_detected_total',
    'Security threats detected by pattern',
    ['pattern_type']
)

# ========================================
# BLACKLIST PATTERNS
# ========================================

BLACKLIST_PATTERNS = [
    (r'select\s+.*from', 'sql_injection'),
    (r'drop\s+table', 'sql_injection'),
    (r'union\s+select', 'sql_injection'),
    (r'insert\s+into', 'sql_injection'),
    (r'delete\s+from', 'sql_injection'),
    (r'update\s+.*set', 'sql_injection'),
    (r'--', 'sql_comment'),
    (r'/\*.*\*/', 'sql_comment'),
    (r'<script', 'xss'),
    (r'</script>', 'xss'),
    (r'javascript:', 'xss'),
    (r'onerror\s*=', 'xss'),
    (r'onload\s*=', 'xss'),
    (r'onclick\s*=', 'xss'),
    (r'<iframe', 'xss'),
    (r'eval\(', 'code_injection'),
    (r'exec\(', 'code_injection'),
    (r'\bor\b\s+\d+\s*=\s*\d+', 'sql_injection'),
    (r'\band\b\s+\d+\s*=\s*\d+', 'sql_injection'),
    (r'\.\.\/', 'path_traversal'),
    (r'base64,', 'data_uri'),
    (r'http://', 'external_url'),
    (r'https://', 'external_url'),
    (r'file://', 'file_uri'),
]


def validate_user_input(text: str) -> str:
    """
    Validate and sanitize user input for security threats.
    
    This function replaces the Validation Service microservice.
    Checks for: SQL injection, XSS, script injection, path traversal.
    
    Args:
        text: User input to validate
        
    Returns:
        Sanitized text if valid
        
    Raises:
        ValueError: If security threat detected
    """
    # Length validation
    if not text or not text.strip():
        security_validation_total.labels(status='blocked').inc()
        raise ValueError("Input cannot be empty")
    
    if len(text) > 5000:
        security_validation_total.labels(status='blocked').inc()
        raise ValueError("Input too long (max 5000 characters)")
    
    # Check blacklist patterns
    text_lower = text.lower()
    for pattern, pattern_type in BLACKLIST_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            security_threats_detected.labels(pattern_type=pattern_type).inc()
            security_validation_total.labels(status='blocked').inc()
            
            logger.warning(
                f"Security threat detected: type={pattern_type}, "
                f"pattern={pattern}, input={text[:50]}..."
            )
            
            raise ValueError(
                f"Security threat detected: potential {pattern_type}. "
                "Please rephrase your message without special characters or commands."
            )
    
    # Check for excessive special characters
    special_chars = sum(
        1 for c in text 
        if not c.isalnum() and c not in ' .,!?-—()[]{}"\':;№'
    )
    if special_chars > len(text) * 0.3:
        security_validation_total.labels(status='blocked').inc()
        raise ValueError(
            "Too many special characters. Please use normal text."
        )
    
    # Sanitize
    sanitized = ' '.join(text.split())  # Remove extra whitespace
    sanitized = re.sub(r'[<>{}]', '', sanitized)  # Remove dangerous chars
    
    security_validation_total.labels(status='passed').inc()
    
    logger.info(
        f"Input validated successfully: length={len(sanitized)}, "
        f"original_length={len(text)}"
    )
    
    return sanitized.strip()


@tool
def validate_input(user_message: str) -> str:
    """
    Validate user input for security before processing.
    
    Use this tool FIRST before any other operation with user input.
    Blocks SQL injection, XSS, and other security threats.
    
    Args:
    user_message: The user's message to validate
    
Returns:
    Sanitized message if safe, error message if blocked
"""
try:
    sanitized = validate_user_input(user_message)
    return f"✅ Input validated and sanitized: {sanitized}"
except ValueError as e:
    return f"🚫 SECURITY BLOCK: {str(e)}"

========================================

VALIDATOR CLASS FOR AGENT EXECUTOR
========================================


class SecurityValidator:


"""

Security validator for agent executor.

Validates input before agent processes it.

Usage:
    validator = SecurityValidator()
    safe_input = validator.validate(user_input)
"""

@staticmethod
def validate(text: str) -> str:
    """
    Validate and return sanitized text.
    
    Args:
        text: User input to validate
        
    Returns:
        Sanitized text
        
    Raises:
        ValueError: If security threat detected
    """
    return validate_user_input(text)

@staticmethod
def is_safe(text: str) -> bool:
    """
    Check if input is safe without raising exception.
    
    Args:
        text: User input to check
        
    Returns:
        True if safe, False if threat detected
    """
    try:
        validate_user_input(text)
        return True
    except ValueError:
        return False

@staticmethod
def get_validation_stats() -> dict:
    """
    Get validation statistics from Prometheus metrics.
    
    Returns:
        Dictionary with validation stats
    """
    return {
        "total_validations": security_validation_total._value.get(),
        "threats_detected": security_threats_detected._value.get()
    }
