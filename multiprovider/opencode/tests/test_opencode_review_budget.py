"""Cupo OpenCode de correcciones y re-reviews. Sin red, sin Jira y sin LLM.

Misma semántica que LicitacionesScrapping PR #63 (commit 467995a). Las rutas
son las de esta plantilla: el paquete cuelga de multiprovider/opencode y el
contrato portable de multiprovider/contracts.
"""
import importlib.util
import unittest
from pathlib import Path

# tests/ -> opencode package -> multiprovider -> contracts repo root.
ROOT = Path(__file__).resolve().parents[3]
P = ROOT / "multiprovider" / "opencode" / "automation" / "opencode" / "review_budget.py"
spec = importlib.util.spec_from_file_location("opencode_review_budget", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CupoPublicadoTests(unittest.TestCase):
    def test_los_tres_enteros_son_3_correcciones_3_rereviews_y_4_reviews(self):
        self.assertEqual(mod.MAX_CORRECTIONS, 3)
        self.assertEqual(mod.MAX_RE_REVIEWS, 3)
        self.assertEqual(mod.MAX_TOTAL_REVIEWS, 4)
        self.assertEqual(mod.MAX_TOTAL_REVIEWS, 1 + mod.MAX_RE_REVIEWS)

    def test_las_marcas_publicadas_coinciden_con_esos_enteros(self):
        self.assertEqual(mod.MARCA_CORRECCIONES, "MAX_CORRECTIONS=3")
        self.assertEqual(mod.MARCA_REREVIEWS, "MAX_RE_REVIEWS=3")
        self.assertEqual(mod.MARCA_TOTAL, "MAX_TOTAL_REVIEWS=4")


class DecisionTests(unittest.TestCase):
    def test_pass_inicial_acepta_sin_gastar_correccion(self):
        self.assertEqual(mod.decidir_tras_review("PASS", 0, 1), "aceptar")

    def test_pass_durante_los_tres_ciclos(self):
        # Review 2, 3 y 4 son las re-reviews de los ciclos 1, 2 y 3.
        self.assertEqual(mod.decidir_tras_review("PASS", 1, 2), "aceptar")
        self.assertEqual(mod.decidir_tras_review("PASS", 2, 3), "aceptar")
        self.assertEqual(mod.decidir_tras_review("PASS", 3, 4), "aceptar")

    def test_changes_requested_abre_los_tres_ciclos(self):
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 0, 1), "corregir")
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 1, 2), "corregir")
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 2, 3), "corregir")

    def test_bloqueo_tras_el_tercer_ciclo_si_sigue_changes_requested(self):
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 3, 4), "bloquear")

    def test_historia_agotada_paso_a_paso(self):
        historia = (
            ("CHANGES_REQUESTED", 0, 1, "corregir"),
            ("CHANGES_REQUESTED", 1, 2, "corregir"),
            ("CHANGES_REQUESTED", 2, 3, "corregir"),
            ("CHANGES_REQUESTED", 3, 4, "bloquear"),
        )
        for veredicto, correcciones, review, esperado in historia:
            with self.subTest(correcciones=correcciones, review=review):
                self.assertEqual(
                    mod.decidir_tras_review(veredicto, correcciones, review),
                    esperado,
                )

    def test_el_cupo_anterior_de_una_rereview_bloquea_antes_del_segundo_ciclo(self):
        # Política que agotó KAN-58: 1 re-review. Tras la review 2 ya no corrige.
        self.assertEqual(
            mod.decidir_tras_review("CHANGES_REQUESTED", 0, 1, max_re_reviews=1),
            "corregir",
        )
        self.assertEqual(
            mod.decidir_tras_review("CHANGES_REQUESTED", 1, 2, max_re_reviews=1),
            "bloquear",
        )
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 1, 2), "corregir")

    def test_un_techo_de_tres_reviews_totales_bloquea_el_tercer_ciclo(self):
        # max_re_reviews=2 ⇒ 3 reviews en total. Tras la review 3 no cabe la 4.ª,
        # así que no arranca la tercera corrección.
        self.assertEqual(
            mod.decidir_tras_review("CHANGES_REQUESTED", 2, 3, max_re_reviews=2),
            "bloquear",
        )
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 2, 3), "corregir")

    def test_una_sola_correccion_bloquea_aunque_queden_reviews(self):
        self.assertEqual(
            mod.decidir_tras_review(
                "CHANGES_REQUESTED", 1, 2, max_corrections=1, max_re_reviews=3
            ),
            "bloquear",
        )
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 1, 2), "corregir")

    def test_pass_de_la_cuarta_review_no_se_confunde_con_el_bloqueo(self):
        self.assertEqual(mod.decidir_tras_review("PASS", 3, 4), "aceptar")
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 3, 4), "bloquear")

    def test_una_quinta_review_no_se_acepta(self):
        self.assertEqual(mod.decidir_tras_review("PASS", 4, 5), "bloquear")
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 4, 5), "bloquear")

    def test_veredicto_blocked_no_abre_correccion(self):
        self.assertEqual(mod.decidir_tras_review("BLOCKED", 0, 1), "bloquear")
        self.assertEqual(mod.decidir_tras_review("BLOCKED", 1, 2), "bloquear")

    def test_contadores_desfasados_bloquean(self):
        self.assertEqual(mod.decidir_tras_review("PASS", 0, 2), "bloquear")
        self.assertEqual(mod.decidir_tras_review("CHANGES_REQUESTED", 2, 2), "bloquear")

    def test_rechaza_veredicto_o_contadores_invalidos(self):
        with self.assertRaises(ValueError):
            mod.decidir_tras_review("pass", 0, 1)
        with self.assertRaises(ValueError):
            mod.decidir_tras_review("CHANGES_REQUESTED", -1, 1)
        with self.assertRaises(ValueError):
            mod.decidir_tras_review("PASS", 0, 0)
        with self.assertRaises(ValueError):
            mod.decidir_tras_review("PASS", True, 1)


class TextosTests(unittest.TestCase):
    def test_una_frase_antigua_de_review_se_detecta(self):
        texto = (
            "MAX_CORRECTIONS=3 MAX_RE_REVIEWS=3 MAX_TOTAL_REVIEWS=4 "
            "automation/opencode/review_budget.py at most ONE NEW reviewer"
        )
        errores = mod.texto_respeta_cupo(texto, ("ONE NEW reviewer",))
        self.assertTrue(any("ONE NEW reviewer" in e for e in errores))

    def test_textos_del_repo_coinciden_con_el_cupo(self):
        mod.verificar_textos(ROOT)

    def test_el_preflight_exige_el_cupo(self):
        src = (ROOT / "multiprovider" / "opencode" / "automation" / "opencode" / "check_config.py").read_text(encoding="utf-8")
        self.assertIn("verificar_textos", src)
        main = src.split("def main", 1)[1]
        self.assertLess(main.index("_verificar_cupo_de_review"), main.index("require_opencode_go_models"))

    def test_las_rutas_son_las_de_la_plantilla(self):
        unidos = "\n".join(mod.ARCHIVOS_CON_CUPO)
        self.assertIn("multiprovider/opencode/MIGRACION.md", unidos)
        self.assertIn("multiprovider/opencode/PRUEBAS-Y-ARRANQUE-LIMPIO.md", unidos)
        self.assertIn("multiprovider/contracts/PORTABLE-CONTRACT.md", unidos)
        self.assertIn("multiprovider/opencode/.github/workflows/opencode-factory-PILOT.yml", unidos)
        self.assertNotIn("automation/opencode/docs/", unidos)
        self.assertNotIn("\ncontracts/PORTABLE-CONTRACT.md", "\n" + unidos)

    def test_decidir_tras_review_no_ejecuta_el_bucle(self):
        runner = (ROOT / "multiprovider" / "opencode" / "automation" / "opencode" / "guarded_run.py").read_text(encoding="utf-8")
        preflight = (ROOT / "multiprovider" / "opencode" / "automation" / "opencode" / "check_config.py").read_text(encoding="utf-8")
        self.assertNotIn("decidir_tras_review", runner)
        self.assertNotIn("decidir_tras_review(", preflight)
        self.assertIn("verificar_textos", preflight)


if __name__ == "__main__":
    unittest.main()
