"""Automated tests for static frontend assets and deployment configuration."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent.parent


class TestFrontendAssets(unittest.TestCase):

    def test_deploy_workflow(self):
        """GitHub Actions deploy.yml must use actions/checkout@v4 and valid GitHub Pages steps."""
        deploy_yml = ROOT / ".github" / "workflows" / "deploy.yml"
        self.assertTrue(deploy_yml.exists())
        content = deploy_yml.read_text(encoding="utf-8")
        self.assertIn("actions/checkout@v4", content)
        self.assertNotIn("actions/checkout@v6", content)
        self.assertIn("actions/deploy-pages@v4", content)

    def test_index_html_elements(self):
        """index.html must contain required branding, badges, IDs, and structure."""
        html_path = ROOT / "index.html"
        self.assertTrue(html_path.exists())
        content = html_path.read_text(encoding="utf-8")

        # Required text & badges
        self.assertIn("SYNTHETIC DATA", content)
        self.assertIn("Civic Operations Intelligence", content)
        self.assertIn("Where should we fix first?", content)

        # Exploration controls
        self.assertIn('id="searchInput"', content)
        self.assertIn('id="zoneFilter"', content)
        self.assertIn('id="issueFilter"', content)
        self.assertIn('id="severityFilter"', content)
        self.assertIn('id="resetFilters"', content)
        self.assertIn('id="matchingCount"', content)

        # Priority Queue & Detail Card
        self.assertIn('id="queueRows"', content)
        self.assertIn('id="detailCard"', content)
        self.assertIn('id="detailPriority"', content)
        self.assertIn('id="detailReasons"', content)
        self.assertIn('id="saveDecision"', content)

        # ML Forecast & Assistant
        self.assertIn('id="forecast"', content)
        self.assertIn('id="modelMae"', content)
        self.assertIn('id="baselineMae"', content)
        self.assertIn('id="assistantForm"', content)
        self.assertIn('id="assistantInput"', content)

    def test_css_variables_and_theme(self):
        """styles.css must implement clean light theme variables without broken selectors."""
        css_path = ROOT / "styles.css"
        self.assertTrue(css_path.exists())
        content = css_path.read_text(encoding="utf-8")

        self.assertIn("--bg-app: #f8fafc;", content)
        self.assertIn("--bg-card: #ffffff;", content)
        self.assertIn("--primary: #2563eb;", content)
        self.assertIn("--success: #16a34a;", content)
        self.assertIn("--danger: #dc2626;", content)

    def test_relative_paths_for_github_pages(self):
        """HTML must use relative asset paths suitable for /cityfix-ai/ deployment."""
        content = (ROOT / "index.html").read_text(encoding="utf-8")
        # Check href and src attributes do not start with absolute '/'
        absolute_hrefs = re.findall(r'(?:href|src)=["\']/(?![/])', content)
        self.assertEqual(len(absolute_hrefs), 0, f"Found absolute paths: {absolute_hrefs}")


if __name__ == "__main__":
    unittest.main()
