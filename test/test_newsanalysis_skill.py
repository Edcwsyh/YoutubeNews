import re
import unittest
from pathlib import Path


SKILL_FILE = (
    Path(__file__).resolve().parent.parent
    / ".opencode" / "skills" / "newsanalysis" / "SKILL.md"
)


class NewsAnalysisSkillStructureTests(unittest.TestCase):
    """Check the skill document's structure, not generated report quality."""

    @classmethod
    def setUpClass(cls):
        cls.content = SKILL_FILE.read_text(encoding="utf-8")

    def test_frontmatter_has_skill_name_and_description(self):
        frontmatter = re.match(r"\A---\n(.*?)\n---\n", self.content, re.DOTALL)
        self.assertIsNotNone(frontmatter)
        fields = dict(
            line.split(": ", 1) for line in frontmatter.group(1).splitlines()
        )
        self.assertEqual(fields["name"], "newsanalysis")
        self.assertTrue(fields["description"].strip())

    def test_instruction_sections_are_not_duplicated(self):
        headings = re.findall(r"^## (.+)$", self.content, re.MULTILINE)
        self.assertGreater(len(headings), 0)
        self.assertEqual(len(headings), len(set(headings)))
        self.assertEqual(headings.count("报告结构"), 1)

    def test_report_structure_matches_readable_reference_layout(self):
        headings = re.findall(r"^### (.+)$", self.content, re.MULTILINE)
        self.assertEqual(headings, [
            "本期的主题",
            "1.1 本期主题发生了什么事情，博主的核心观点是什么",
            "1.2 AI搜索资料针对本期主题的分析",
            "2. 本期的新闻总览",
            "3. 视频总体评价",
        ])
        report_section = self.content.split("## 报告结构\n", 1)[1].split("\n## ", 1)[0]
        self.assertEqual(
            re.findall(r"^### (.+)$", report_section, re.MULTILINE),
            headings,
        )

    def test_ai_analysis_has_background_logic_fact_check_and_outlook(self):
        self.assertEqual(
            re.findall(r"^#### (.+)$", self.content, re.MULTILINE),
            ["背景补充", "逻辑评论", "数据核查", "趋势研判"],
        )


if __name__ == "__main__":
    unittest.main()
