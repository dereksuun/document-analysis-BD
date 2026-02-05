from django.test import SimpleTestCase

from documents.services import sanitize_payload


class SanitizePayloadTests(SimpleTestCase):
    def test_preserves_ai_sections_when_present(self):
        payload = {
            "document_type": "curriculo",
            "fields": {"document_value": "10.00"},
            "custom_fields": {},
            "ai": {
                "doc_type": "curriculo",
                "person": {
                    "name": "Maria",
                    "emails": ["maria@email.com"],
                    "phones": [],
                    "location": None,
                    "age_estimate_years": None,
                    "age_evidence": None,
                },
                "experience": {
                    "years_estimate": 5,
                    "years_evidence": "2019-2024",
                    "seniority": "pleno",
                    "roles": ["Backend"],
                    "companies": ["Empresa X"],
                },
                "skills": [],
                "education": [],
                "keywords_evidence": [],
                "confidence": {"overall": 0.8},
            },
            "ai_meta": {
                "model": "gpt-5-mini",
                "schema_version": "2026-02-02.v1",
                "created_at": "2026-02-02T00:00:00+00:00",
                "ignore_me": "x",
            },
        }

        cleaned = sanitize_payload(payload)
        self.assertIn("ai", cleaned)
        self.assertIn("ai_meta", cleaned)
        self.assertEqual(cleaned["ai"]["doc_type"], "curriculo")
        self.assertNotIn("ignore_me", cleaned["ai_meta"])
