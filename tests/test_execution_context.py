from scripts.verify import execution_context


def test_local_execution_cannot_be_presented_as_hosted(monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", "phlppgdfry/quayready")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    assert execution_context() == {"executionEnvironment": "LOCAL", "hostedRunUrl": None}


def test_hosted_job_reference_is_not_a_workflow_success_claim(monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REPOSITORY", "phlppgdfry/quayready")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    assert execution_context() == {
        "executionEnvironment": "GITHUB_ACTIONS",
        "hostedRunUrl": "https://github.com/phlppgdfry/quayready/actions/runs/123",
    }
    monkeypatch.setenv("GITHUB_REPOSITORY", "https://untrusted.invalid")
    assert execution_context()["hostedRunUrl"] is None
