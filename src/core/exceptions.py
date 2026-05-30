"""Diagnostic Service — Custom exception hierarchy"""


class DiagnosticError(Exception):
    def __init__(self, message: str, code: str = "DIAGNOSTIC_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class SessionNotFoundError(DiagnosticError):
    def __init__(self, session_id: str):
        super().__init__(f"Session {session_id} not found", "SESSION_NOT_FOUND")


class SessionExpiredError(DiagnosticError):
    def __init__(self, session_id: str):
        super().__init__(
            f"Session {session_id} expired or not in Redis", "SESSION_EXPIRED"
        )


class SessionAlreadyCompletedError(DiagnosticError):
    def __init__(self, session_id: str):
        super().__init__(
            f"Session {session_id} is already completed", "SESSION_COMPLETED"
        )


class NoTasksAvailableError(DiagnosticError):
    def __init__(self, skill_id: str):
        super().__init__(
            f"No tasks available for skill {skill_id}", "NO_TASKS"
        )


class InvalidAnswerError(DiagnosticError):
    def __init__(self, detail: str):
        super().__init__(detail, "INVALID_ANSWER")


class GradeNotConfiguredError(DiagnosticError):
    def __init__(self, grade: int):
        super().__init__(
            f"Grade {grade} has no topics configured in knowledge_hierarchy",
            "GRADE_NOT_CONFIGURED",
        )
