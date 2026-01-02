"""
Request and response models for Radio Free Luna API

Provides validated data models for all API endpoints using simple, portable validation.
No heavy dependencies - all validation done with pure Python.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime


class ValidationError(Exception):
    """Custom validation error"""
    pass


class SessionRequest:
    """Validated request for creating a DJ session"""

    def __init__(self, theme: str, duration_minutes: int):
        self.theme = self._validate_theme(theme)
        self.duration_minutes = self._validate_duration(duration_minutes)

    @staticmethod
    def _validate_theme(theme: str) -> str:
        """Validate and sanitize theme parameter"""
        if not isinstance(theme, str):
            raise ValidationError("Theme must be a string")

        # Strip whitespace
        theme = theme.strip()

        # Check length
        if len(theme) < 1:
            raise ValidationError("Theme cannot be empty")
        if len(theme) > 100:
            raise ValidationError("Theme too long (max 100 characters)")

        # Only allow alphanumeric and basic punctuation
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' ")
        for char in theme:
            if char not in allowed_chars:
                raise ValidationError(
                    f"Theme contains invalid character: '{char}'. "
                    "Only alphanumeric, underscore, hyphen, and space allowed."
                )

        return theme

    @staticmethod
    def _validate_duration(duration: Any) -> int:
        """Validate and convert duration parameter"""
        try:
            if isinstance(duration, str):
                duration = int(duration)
            elif not isinstance(duration, int):
                duration = int(duration)
        except (ValueError, TypeError):
            raise ValidationError("Duration must be an integer")

        # Check range
        if duration < 5:
            raise ValidationError("Session duration must be at least 5 minutes")
        if duration > 480:
            raise ValidationError("Session duration cannot exceed 480 minutes (8 hours)")

        return duration


class TestVoiceRequest:
    """Validated request for testing voice synthesis"""

    def __init__(self, text: str):
        self.text = self._validate_text(text)

    @staticmethod
    def _validate_text(text: str) -> str:
        """Validate and sanitize TTS input text"""
        if not isinstance(text, str):
            raise ValidationError("Text must be a string")

        # Strip whitespace
        text = text.strip()

        # Check length
        if len(text) < 1:
            raise ValidationError("Text cannot be empty")
        if len(text) > 1000:
            raise ValidationError("Text too long (max 1000 characters)")

        # Warn about extreme length but don't reject
        if len(text) > 500:
            # Still allowed, but warn that it will take longer
            pass

        return text


class CommentaryRequest:
    """Validated request for generating commentary"""

    def __init__(self, text_type: str = "contextual"):
        self.text_type = self._validate_text_type(text_type)

    @staticmethod
    def _validate_text_type(text_type: str) -> str:
        """Validate commentary type"""
        allowed_types = ["contextual", "opening", "transition", "closing"]

        if not isinstance(text_type, str):
            raise ValidationError("text_type must be a string")

        text_type = text_type.strip().lower()

        if text_type not in allowed_types:
            raise ValidationError(
                f"Invalid text_type '{text_type}'. "
                f"Allowed values: {', '.join(allowed_types)}"
            )

        return text_type


class HealthCheckResponse:
    """Response model for health check endpoint"""

    def __init__(self):
        self.timestamp = datetime.utcnow().isoformat()
        self.status = "healthy"
        self.version = "1.0.0"
        self.system = "Radio Free Luna"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "timestamp": self.timestamp,
            "status": self.status,
            "version": self.version,
            "system": self.system,
        }


class ValidationHelpers:
    """Helper functions for request validation"""

    @staticmethod
    def validate_request(request_class, **kwargs) -> object:
        """Validate a request and return validated instance or raise ValidationError"""
        try:
            return request_class(**kwargs)
        except ValidationError as e:
            # Re-raise with additional context
            raise ValidationError(f"Validation failed: {str(e)}")
        except Exception as e:
            raise ValidationError(f"Unexpected error during validation: {str(e)}")

    @staticmethod
    def get_validation_error_response(error: ValidationError) -> Dict[str, Any]:
        """Convert validation error to API response"""
        return {
            "error": "Validation Failed",
            "detail": str(error),
            "status_code": 422,
        }
