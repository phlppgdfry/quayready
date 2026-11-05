from scripts.verify import execution_context


def test_public_snapshot_excludes_private_evidence_and_identifies_release(tmp_path, monkeypatch):
    import json

    from scripts import build_showcase

    evidence = tmp_path / "evidence/rc"
    evidence.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="0.2.0rc1"\n')
    (evidence / "pytest.xml").write_text('<testsuites><testsuite tests="1"/></testsuites>')
    (evidence / "execution.json").write_text(
        json.dumps(
            {
                "executedAt": "2026-11-05T09:00:00Z",
                "result": "PASS",
                "python": "3.13.18",
                "gitHeadAtExecution": "a" * 40,
                "platform": "PRIVATE-MACHINE-SENTINEL",
                "artifacts": [{"artifact": "/private/PRIVATE-PATH-SENTINEL"}],
                "privateToken": "PRIVATE-TOKEN-SENTINEL",
            }
        )
    )
    monkeypatch.setattr(build_showcase, "ROOT", tmp_path)
    public = build_showcase.snapshot()
    assert public["version"] == "0.2.0rc1"
    assert public["sourceCommit"] == "a" * 40
    assert "PRIVATE-" not in json.dumps(public)


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
