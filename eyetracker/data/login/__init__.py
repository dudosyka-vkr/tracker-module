"""Login submodule."""

from eyetracker.data.login.local_service import LocalLoginService
from eyetracker.data.login.service import AuthResult, LoginService

__all__ = ["AuthResult", "LoginService", "LocalLoginService"]
