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


class SessionAlreadyStartedError(DiagnosticError):
    """An invite already owns another unfinished diagnostic session."""

    def __init__(self, session_id: str):
        super().__init__(
            f"Diagnostic invite already belongs to session {session_id}",
            "SESSION_ALREADY_STARTED",
        )


class NoTasksAvailableError(DiagnosticError):
    def __init__(self, skill_id: str):
        super().__init__(
            f"No tasks available for skill {skill_id}", "NO_TASKS"
        )


class InvalidAnswerError(DiagnosticError):
    def __init__(self, detail: str):
        super().__init__(detail, "INVALID_ANSWER")


class TaskOutOfSequenceError(DiagnosticError):
    """An answer was submitted for a task other than the active task."""

    def __init__(self, session_id: str):
        super().__init__(
            f"Answer does not match the current task for session {session_id}",
            "TASK_OUT_OF_SEQUENCE",
        )


class AnswerInProgressError(DiagnosticError):
    """A second request arrived while the current answer is being processed."""

    def __init__(self, session_id: str):
        super().__init__(
            f"Answer submission is already in progress for session {session_id}",
            "ANSWER_IN_PROGRESS",
        )


class GradeNotConfiguredError(DiagnosticError):
    def __init__(self, grade: int):
        super().__init__(
            f"Grade {grade} has no topics configured in knowledge_hierarchy",
            "GRADE_NOT_CONFIGURED",
        )
