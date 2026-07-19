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


def test_extract_resume_profile_uses_experience_as_summary_and_repairs_pdf_skill_spacing() -> None:
    profile = extract_resume_profile(
        """
        技能
        用户调研、工具、Py thon、Ja v aScrip t
        工作经历
        平台 产品经 理，小米科技 | 2024.08 - 至今
        负责 AI Agent 产品设计与交付
        教育经历
        景观建筑硕士；W ebsite: www.sno wguo.c om；密歇根安娜堡大学；2021.09 - 2024.05
        """
    )

    assert profile["summary"] == "平台产品经理，小米科技 | 2024.08 - 至今；负责 AI Agent 产品设计与交付"
    assert profile["skills"] == ["用户调研", "Python", "JavaScript"]
    assert profile["education"] == "景观建筑硕士；密歇根安娜堡大学；2021.09 - 2024.05"


def test_extract_resume_profile_ignores_repeated_pdf_obfuscation_markers() -> None:
    marker = "bf63fd04e3f2ddac1HJ-3Ni8EFBSwYm9V_6cWOGnn_HZMhll"
    profile = extract_resume_profile(
        f"""
        个人简介
        负责企业财务系统搭建和流程优化。
        {marker}
        {marker}
        工作经历
        2022.01-至今 某科技公司 财务经理
        {marker}
        {marker}
        教育经历
        2014.09-2018.06 某大学 会计学 本科
        {marker}
        {marker}
        """
    )

    assert profile["summary"] == "负责企业财务系统搭建和流程优化。"
    assert profile["experience"] == "2022.01-至今 某科技公司 财务经理"
    assert profile["education"] == "2014.09-2018.06 某大学 会计学 本科"
    assert marker not in str(profile)


def test_extract_resume_profile_repairs_legacy_boss_trailing_section_headings() -> None:
    profile = extract_resume_profile(
        """
        求 职 信 息
        工 作 时 长 ： 22 年
        求 职 意 向 ： 财 务 经 理 / 主 管
        期 望 城 市 ： 深 圳
        熟 练 操 作 上 市 公 司 生 产 制 造 业 全 盘 帐 务 处 理 工 作 。
        具 有 良 好 的 职 业 道 德 和 职 业 操 守 ， 严 谨 细 致 ， 善 于 沟 通 。
        个 人 优 势
        深 圳 博 雅 英 杰 电 子 有 限 公 司 财 务 经 理 / 主 管 2 0 1 8 . 0 8 - 至 今
        1 、 负 责 上 市 公 司 全 盘 帐 务 处 理 。
        工 作 经 历
        2 、 建 立 健 全 财 务 系 统 。
        四 川 大 学 大 专 会 计 1 9 9 6 - 1 9 9 8
        教 育 经 历
        """
    )

    assert profile["summary"] == "熟练操作上市公司生产制造业全盘帐务处理工作。具有良好的职业道德和职业操守，严谨细致，善于沟通。"
    assert profile["experience"] == "深圳博雅英杰电子有限公司财务经理/主管 2018.08 - 至今；1、负责上市公司全盘帐务处理。；2、建立健全财务系统。"
    assert profile["education"] == "四川大学 大专 会计 1996-1998"


def test_extract_resume_profile_prepends_school_before_trailing_education_heading() -> None:
    profile = extract_resume_profile(
        """
        工作经历
        某公司 采购专员
        深圳信息职业技术学院 大专 室内环境检测与控制技术 2017-2020
        教育经历
        在校担任书法协会组织部副部长，负责活动筹备工作。
        """
    )

    assert profile["experience"] == "某公司 采购专员"
    assert profile["education"] == "深圳信息职业技术学院 大专 室内环境检测与控制技术 2017-2020；在校担任书法协会组织部副部长，负责活动筹备工作。"
