import pytest
from fastapi import HTTPException

from prd_engine.models.workflow import WorkflowStatus
from prd_engine.services.workflow import validate_status_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (WorkflowStatus.PENDING, WorkflowStatus.RUNNING),
        (WorkflowStatus.PENDING, WorkflowStatus.CANCELLED),
        (WorkflowStatus.PENDING, WorkflowStatus.FAILED),
        (WorkflowStatus.RUNNING, WorkflowStatus.COMPLETED),
        (WorkflowStatus.RUNNING, WorkflowStatus.FAILED),
        (WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED),
        (WorkflowStatus.FAILED, WorkflowStatus.PENDING),
        (WorkflowStatus.PENDING, WorkflowStatus.PENDING),
    ],
)
def test_allowed_workflow_transitions(current, target):
    validate_status_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (WorkflowStatus.COMPLETED, WorkflowStatus.RUNNING),
        (WorkflowStatus.COMPLETED, WorkflowStatus.PENDING),
        (WorkflowStatus.CANCELLED, WorkflowStatus.RUNNING),
        (WorkflowStatus.CANCELLED, WorkflowStatus.PENDING),
        (WorkflowStatus.RUNNING, WorkflowStatus.PENDING),
        (WorkflowStatus.PENDING, WorkflowStatus.COMPLETED),
        (WorkflowStatus.FAILED, WorkflowStatus.COMPLETED),
    ],
)
def test_invalid_workflow_transitions_return_conflict(current, target):
    with pytest.raises(HTTPException) as exc:
        validate_status_transition(current, target)

    assert exc.value.status_code == 409
