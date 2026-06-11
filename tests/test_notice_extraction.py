from __future__ import annotations

import unittest

from app.normalization import extract_events_from_text
from app.normalization import extract_review_hints_from_text


DOC_882_TITLE = "奥康国际第八届董事会提名委员会2025年第三次会议决议"
DOC_882_BODY = """
浙江奥康鞋业股份有限公司第八届董事会提名委员会 2025 年第三次会议决议。
经公司董事会提名委员会审查，同意提名王振滔、王进权、余雄平、王晨为第九届董事会非独立董事候选人，
提名周俊明、Bingsheng Teng、林宗纯为第九届董事会独立董事候选人。
"""

DOC_904_TITLE = "第七届董事会第六次会议决议公告"
DOC_904_BODY = """
1、审议通过《关于聘任财务总监的议案》。
由公司总经理张文先生提名，经公司第七届董事会提名委员会第二次会议审议通过，
亦经第七届董事会审计委员会第三次会议审议通过，公司聘任曹锐先生担任公司财务总监，负责公司财务工作。
"""

DOC_910_TITLE = "第五届董事会第九次会议决议公告"
DOC_910_BODY = """
（一）审议通过《关于聘任公司副总经理及部分副总经理薪酬的议案》
经公司总经理提名并经董事会提名委员会审核，董事会同意聘任李一芃先生担任公司副总经理，
任期自本次董事会审议通过之日起至第五届董事会任期届满之日止。
"""

DOC_912_TITLE = "第五届董事会第十三次会议决议公告"
DOC_912_BODY = """
1、审议通过《关于前期会计差错更正及追溯调整的议案》。
本议案已经第五届董事会审计委员会审议通过。
"""

DOC_768_TITLE = "无锡路通视信网络股份有限公司第五届董事会第二十二次会议决议公告"
DOC_768_BODY = """
1、审议通过了《关于补选于涛先生为公司第五届董事会非独立董事的议案》
根据《公司法》和《公司章程》的有关规定，经持有公司 10.46%股份的股东吴世春推荐、第五届董事会提名委员会审核，
董事会同意补选于涛先生为公司第五届董事会非独立董事候选人，任期自公司股东会审议通过之日起至第五届董事会届满之日止。
"""


class NoticeExtractionTests(unittest.TestCase):
    def test_nomination_list_supports_independent_and_english_names(self) -> None:
        events = extract_events_from_text(DOC_882_TITLE, DOC_882_BODY)
        normalized = {(item.person_name, item.role_canonical, item.event_type) for item in events}
        self.assertEqual(len(events), 7)
        self.assertIn(("王振滔", "director", "nomination"), normalized)
        self.assertIn(("周俊明", "independent_director", "nomination"), normalized)
        self.assertIn(("Bingsheng Teng", "independent_director", "nomination"), normalized)
        self.assertNotIn(("产生", "director", "appointment"), normalized)

    def test_cfo_appointment_extracts_target_person(self) -> None:
        events = extract_events_from_text(DOC_904_TITLE, DOC_904_BODY)
        self.assertEqual(
            [(item.person_name, item.role_canonical, item.event_type) for item in events],
            [("曹锐", "cfo_equivalent", "appointment")],
        )

    def test_senior_management_appointment_is_detected(self) -> None:
        events = extract_events_from_text(DOC_910_TITLE, DOC_910_BODY)
        self.assertEqual(
            [(item.person_name, item.role_canonical, item.event_type) for item in events],
            [("李一芃", "senior_management", "appointment")],
        )

    def test_non_management_notice_returns_no_events(self) -> None:
        self.assertEqual(extract_events_from_text(DOC_912_TITLE, DOC_912_BODY), [])

    def test_board_supplement_extracts_director_candidate(self) -> None:
        events = extract_events_from_text(DOC_768_TITLE, DOC_768_BODY)
        self.assertEqual(
            [(item.person_name, item.role_canonical, item.event_type) for item in events],
            [("于涛", "director", "appointment")],
        )

    def test_vote_summary_without_names_does_not_create_hint(self) -> None:
        """议案标题句（如"审议通过了《关于提名...的议案》"）含人事关键词但无具体人名，
        不应生成"缺失字段：人员姓名" hint 进入 review 队列。"""
        hints = extract_review_hints_from_text(
            "第十届董事会第十三次会议决议公告",
            "（一）审议通过了《关于提名公司第十一届董事会非独立董事候选人的议案》",
        )
        bad_hints = [
            h for h in hints
            if h.person_name is None and "人员姓名" in h.missing_fields
        ]
        self.assertEqual(bad_hints, [])

    def test_rule_normalize_rejects_经公(self) -> None:
        """规则路径的 _normalize_person_name 必须拒绝"经公"等由'经'+后随字组成的假人名。
        '经' 作为常见介词不应被当作人名首字。"""
        from app.normalization import _normalize_person_name
        self.assertIsNone(_normalize_person_name("经公"))
        self.assertIsNone(_normalize_person_name("经董事会"))
        self.assertIsNone(_normalize_person_name("经审查"))
        # 真实名字保留
        self.assertEqual(_normalize_person_name("乔胜俊"), "乔胜俊")
        self.assertEqual(_normalize_person_name("张文"), "张文")

    def test_ai_path_delegates_to_rule_normalize(self) -> None:
        """AI 路径的 _normalize_person_name 必须和规则路径完全等价。
        这保证 '经公' 等假人名在 AI 路径下也被拒绝。"""
        from app.ai_extractor import _normalize_person_name as ai_normalize
        from app.normalization import _normalize_person_name as rule_normalize

        # 假人名 — 两条路径都必须返回 None 且行为一致
        for value in ["经公", "经董事会", "经审查", "经审核", "经公司", ""]:
            self.assertIsNone(ai_normalize(value), f"AI path should reject {value!r}")
            self.assertEqual(ai_normalize(value), rule_normalize(value))

        # 真实名字 — 两条路径都必须返回相同的合法名字
        for value in ["乔胜俊", "杜若榕", "王浩", "刘松", "张文", "曹锐"]:
            self.assertEqual(ai_normalize(value), value)
            self.assertEqual(ai_normalize(value), rule_normalize(value))


if __name__ == "__main__":
    unittest.main()
