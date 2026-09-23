"""Tests for the generated `.importlinter` architecture contracts.

The file is only worth shipping if the project it is generated into actually
satisfies it, so these tests run `lint-imports` against a generated project as
well as checking the rendered configuration.
"""

from __future__ import annotations

import configparser
import os
import shutil
import subprocess
from pathlib import Path

import pytest


def read_contracts(project: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    parser.read(project / ".importlinter", encoding="utf-8")
    return parser


def containers(project: Path) -> list[str]:
    layers = read_contracts(project)["importlinter:contract:layers"]
    return layers["containers"].split()


class TestGeneratedConfiguration:
    def test_always_ships_a_contracts_file(self, generate):
        project = generate()

        assert (project / ".importlinter").exists()

    def test_scans_the_apps_package_and_ignores_type_checking_imports(self, generate):
        section = read_contracts(generate())["importlinter"]

        assert section["root_package"] == "apps"
        assert section["exclude_type_checking_imports"] == "True"

    def test_always_contains_the_apps_that_are_always_generated(self, generate):
        assert set(containers(generate())) >= {"apps.core", "apps.users"}

    def test_includes_optional_apps_only_when_they_are_enabled(self, generate):
        # Distinct slugs: two generations into one temp dir would collide.
        with_all = containers(
            generate(project_slug="with_all", api_style="drf", use_stripe=True, use_teams=True)
        )
        without = containers(
            generate(project_slug="without", api_style="none", use_stripe=False, use_teams=False)
        )

        assert {"apps.api", "apps.billing", "apps.teams"} <= set(with_all)
        assert {"apps.api", "apps.billing", "apps.teams"}.isdisjoint(without)

    def test_guards_the_api_delivery_edge_when_an_api_is_generated(self, generate):
        parsed = read_contracts(generate(api_style="drf"))

        contract = parsed["importlinter:contract:delivery-edges"]
        assert contract["forbidden_modules"].split() == ["apps.api"]
        assert "apps.api" not in contract["source_modules"].split()

    def test_omits_the_delivery_edge_contract_when_there_is_no_api(self, generate):
        parsed = read_contracts(generate(api_style="none"))

        assert "importlinter:contract:delivery-edges" not in parsed

    @pytest.mark.parametrize("manager", ["uv", "poetry"])
    def test_the_hook_runs_through_the_manager(self, generate, manager):
        # Git runs hooks without the project venv activated, so the hook must go
        # through the manager - as the generated CI does for ruff, mypy, pytest.
        project = generate(project_slug=f"hook_{manager}", dependency_manager=manager)

        hook = (project / ".pre-commit-config.yaml").read_text()
        assert f"{manager} run lint-imports --no-logo" in hook

    @pytest.mark.parametrize("manager", ["uv", "poetry"])
    def test_the_recipe_matches_its_sibling_recipes(self, generate, manager):
        # The Justfile is interactive: under poetry every recipe (test, lint,
        # typecheck) calls its tool bare, expecting an activated venv.
        project = generate(project_slug=f"recipe_{manager}", dependency_manager=manager)
        justfile = (project / "Justfile").read_text()

        if manager == "uv":
            assert "uv run lint-imports --no-logo" in justfile
        else:
            assert "PYTHONPATH=. lint-imports --no-logo" in justfile
            assert "\n    pytest\n" in justfile  # the `test` sibling is bare too

    def test_records_no_pre_existing_debt(self, generate):
        parsed = read_contracts(generate(api_style="drf", use_stripe=True, use_teams=True))

        for section in parsed.sections():
            assert "ignore_imports" not in parsed[section], (
                f"{section} ships with recorded debt; a generated project starts clean"
            )


@pytest.mark.skipif(shutil.which("lint-imports") is None, reason="import-linter not installed")
class TestContractsHoldInAGeneratedProject:
    """The contracts must pass on the code the template actually emits."""

    def _lint(self, project: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(shutil.which("lint-imports")), "--no-logo"],
            cwd=project,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(project)},
        )

    def test_a_fully_featured_project_satisfies_its_own_contracts(self, generate):
        project = generate(
            api_style="drf", use_stripe=True, use_teams=True, frontend="htmx-tailwind"
        )

        result = self._lint(project)

        assert result.returncode == 0, result.stdout

    def test_a_boundary_violation_fails_the_check(self, generate):
        # Without this, a misconfigured contract that can never fire would still
        # pass both tests above.
        project = generate(project_slug="violating", api_style="drf")
        models = project / "apps" / "users" / "models.py"
        models.write_text(
            models.read_text() + "\nfrom apps.api import urls as _violation  # noqa\n"
        )

        result = self._lint(project)

        assert result.returncode != 0
        assert "api is a delivery edge - nothing may import it BROKEN" in result.stdout
        assert "apps.users.models -> apps.api.urls" in result.stdout

    def test_a_minimal_project_satisfies_its_own_contracts(self, generate):
        project = generate(api_style="none", use_stripe=False, use_teams=False)

        result = self._lint(project)

        assert result.returncode == 0, result.stdout
