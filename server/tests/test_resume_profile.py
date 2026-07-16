from server.app.recruiting.resume_profile import extract_resume_profile


def test_extract_resume_profile_reads_common_chinese_sections_without_contact_details() -> None:
    profile = extract_resume_profile(
        """
        郭莹雪
        手机：13800000000
        个人简介
        8 年研发经验，负责过企业级 Agent 平台从设计到上线。
        专业技能
        Python、FastAPI、RAG、Docker、Kubernetes
        工作经历
        2021.03-至今 某科技公司 技术负责人
        负责 AI Agent 平台和知识库产品交付
        教育经历
        2012.09-2016.06 浙江大学 计算机科学与技术 本科
        """
    )

    assert profile == {
        "summary": "8 年研发经验，负责过企业级 Agent 平台从设计到上线。",
        "skills": ["Python", "FastAPI", "RAG", "Docker", "Kubernetes"],
        "experience": "2021.03-至今 某科技公司 技术负责人；负责 AI Agent 平台和知识库产品交付",
        "education": "2012.09-2016.06 浙江大学 计算机科学与技术 本科",
        "status": "ready",
    }
    assert "13800000000" not in str(profile)


def test_extract_resume_profile_reports_partial_data_instead_of_placeholder_copy() -> None:
    profile = extract_resume_profile("技能\nPython, SQL")

    assert profile["skills"] == ["Python", "SQL"]
    assert profile["summary"] is None
    assert profile["experience"] is None
    assert profile["education"] is None
    assert profile["status"] == "partial"
