from types import SimpleNamespace

from django.test import SimpleTestCase

from documents.ai_filters import (
    document_passes_semantic_filters,
    find_evidence_snippet,
)


class AIFilterTests(SimpleTestCase):
    def _doc(self, **overrides):
        data = {
            "extracted_json": {},
            "text_content": "",
            "text_content_norm": "",
            "extracted_text": "",
            "extracted_age_years": None,
            "extracted_experience_years": None,
        }
        data.update(overrides)
        return SimpleNamespace(**data)

    def test_terms_use_ai_payload_even_when_raw_text_does_not_match(self):
        doc = self._doc(
            extracted_json={
                "ai": {
                    "doc_type": "curriculo",
                    "person": {
                        "name": None,
                        "emails": [],
                        "phones": [],
                        "location": None,
                        "age_estimate_years": None,
                        "age_evidence": None,
                    },
                    "experience": {
                        "years_estimate": 5,
                        "years_evidence": "Atuou de 2019 a 2024 com backend.",
                        "seniority": "pleno",
                        "roles": ["Desenvolvedor Backend"],
                        "companies": ["Empresa X"],
                    },
                    "skills": [
                        {
                            "name": "FastAPI",
                            "level": "advanced",
                            "evidence": "Projetos com FastAPI e Docker.",
                        }
                    ],
                    "education": [],
                    "keywords_evidence": [],
                    "confidence": {"overall": 0.8},
                }
            },
            text_content_norm="curriculo profissional",
        )

        matched = document_passes_semantic_filters(
            doc,
            terms=["docker"],
            mode="all",
            exclude_terms=[],
            experience_min_years=None,
            experience_max_years=None,
            age_min_years=None,
            age_max_years=None,
            exclude_unknowns=False,
        )
        self.assertTrue(matched)

    def test_range_prefers_ai_experience_over_heuristic_field(self):
        doc = self._doc(
            extracted_experience_years=1,
            extracted_json={
                "ai": {
                    "doc_type": "curriculo",
                    "person": {
                        "name": None,
                        "emails": [],
                        "phones": [],
                        "location": None,
                        "age_estimate_years": None,
                        "age_evidence": None,
                    },
                    "experience": {
                        "years_estimate": 6,
                        "years_evidence": "Trabalhou de 2018 ate atual.",
                        "seniority": "senior",
                        "roles": [],
                        "companies": [],
                    },
                    "skills": [],
                    "education": [],
                    "keywords_evidence": [],
                    "confidence": {"overall": 0.7},
                }
            },
        )

        matched = document_passes_semantic_filters(
            doc,
            terms=[],
            mode="all",
            exclude_terms=[],
            experience_min_years=5,
            experience_max_years=None,
            age_min_years=None,
            age_max_years=None,
            exclude_unknowns=False,
        )
        self.assertTrue(matched)

    def test_exclude_unknowns_blocks_missing_values(self):
        doc = self._doc(extracted_json={"ai": {"person": {}, "experience": {}}})
        matched = document_passes_semantic_filters(
            doc,
            terms=[],
            mode="all",
            exclude_terms=[],
            experience_min_years=3,
            experience_max_years=None,
            age_min_years=None,
            age_max_years=None,
            exclude_unknowns=True,
        )
        self.assertFalse(matched)

    def test_evidence_snippet_prioritizes_matching_term(self):
        doc = self._doc(
            extracted_json={
                "ai": {
                    "doc_type": "curriculo",
                    "person": {
                        "name": None,
                        "emails": [],
                        "phones": [],
                        "location": None,
                        "age_estimate_years": None,
                        "age_evidence": None,
                    },
                    "experience": {
                        "years_estimate": 4,
                        "years_evidence": "Atuacao com APIs.",
                        "seniority": "pleno",
                        "roles": [],
                        "companies": [],
                    },
                    "skills": [
                        {
                            "name": "Docker",
                            "level": "advanced",
                            "evidence": "Experiencia forte com Docker e Kubernetes.",
                        }
                    ],
                    "education": [],
                    "keywords_evidence": [],
                    "confidence": {"overall": 0.9},
                }
            }
        )
        snippet = find_evidence_snippet(doc, ["docker"], max_len=120)
        self.assertIn("Docker", snippet)
