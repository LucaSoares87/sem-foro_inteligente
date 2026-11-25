import copy
import os
from unittest import TestCase, mock
import final_acceptance as app


class AcceptanceIsolationTest(TestCase):
    def config(self):
        return {"name": app.PROJECT, "services": {
            "postgres": {"environment": {"POSTGRES_DB": "traffic"}},
            "migrate": {},
            "backend": {"environment": dict(app.SETTINGS)},
            "frontend": {"ports": [{"host_ip": "127.0.0.1", "published": "5173", "target": 8080}]}
        }, "volumes": {"pgdata": {"name": app.PROJECT + "_pgdata"}}}

    def test_environment_does_not_inherit_field_settings(self):
        with mock.patch.dict(os.environ, {"VIDEO_SOURCES_JSON": "poison", "AUTH_MODE": "proxy_headers",
                 "COMPOSE_FILE": "other.yml", "DOCKER_HOST": "tcp://remote", "POSTGRES_PASSWORD": "poison",
                 "VALIDATION_EVIDENCE_JSON": "poison"}):
            e = app.isolated_env("test-only")
            self.assertEqual(e["VIDEO_SOURCES_JSON"], "[]")
            self.assertEqual(e["VALIDATION_EVIDENCE_JSON"], "[]")
            self.assertEqual(e["AUTH_MODE"], "disabled")
            self.assertEqual(e["POSTGRES_PASSWORD"], "test-only")
            self.assertNotIn("COMPOSE_FILE", e)
            self.assertNotIn("DOCKER_HOST", e)

    def test_config_rejects_field_and_public_port(self):
        app.validate_config(self.config())
        for key, value in (("VIDEO_SOURCES_JSON", "[{}]"), ("VISION_MODEL_JSON", "{}"),
                           ("VALIDATION_EVIDENCE_JSON", "[{}]"), ("AUTH_MODE", "proxy_headers")):
            c = self.config()
            c["services"]["backend"]["environment"][key] = value
            with self.assertRaises(ValueError):
                app.validate_config(c)
        for mut in (lambda c: c["services"]["frontend"]["ports"][0].update(host_ip="0.0.0.0"),
                    lambda c: c["services"]["backend"].update(volumes=[{"source": "/media"}]),
                    lambda c: c["volumes"]["pgdata"].update(external=True),
                    lambda c: c.update(name="other")):
            c = self.config()
            mut(c)
            with self.assertRaises(ValueError):
                app.validate_config(c)
