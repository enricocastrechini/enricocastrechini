import importlib.util
import pathlib
import unittest
import xml.etree.ElementTree as ET

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / '.github' / 'scripts' / 'generate_github_analytics.py'
spec = importlib.util.spec_from_file_location('generate_github_analytics', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FlattenContributionCalendarTests(unittest.TestCase):
    def test_filters_and_sorts_days_from_graphql_calendar(self):
        weeks = [
            {
                'contributionDays': [
                    {'date': '2026-09-17', 'contributionCount': 1},
                    {'date': '2026-09-14', 'contributionCount': 0},
                ]
            },
            {
                'contributionDays': [
                    {'date': '2026-09-16', 'contributionCount': 3},
                    {'date': '2026-09-18', 'contributionCount': 5},
                ]
            },
        ]
        self.assertEqual(
            module.flatten_contribution_calendar(weeks, module.date(2026, 9, 14), module.date(2026, 9, 17)),
            [
                (module.date(2026, 9, 14), 0),
                (module.date(2026, 9, 16), 3),
                (module.date(2026, 9, 17), 1),
            ],
        )


class SummarizeContributionTests(unittest.TestCase):
    def test_current_streak_is_zero_when_latest_day_has_no_contributions(self):
        days = [
            (module.date(2026, 9, 15), 2),
            (module.date(2026, 9, 16), 1),
            (module.date(2026, 9, 17), 0),
        ]
        summary = module.summarize_contributions(days, module.date(2026, 9, 15), module.date(2026, 9, 17))
        self.assertEqual(summary['current_streak'], 0)
        self.assertEqual(summary['longest_streak'], 2)
        self.assertEqual(summary['best_end'], module.date(2026, 9, 16))
        self.assertFalse(summary['current_longest_is_ongoing'])

    def test_current_longest_streak_is_marked_ongoing(self):
        days = [
            (module.date(2026, 9, 15), 0),
            (module.date(2026, 9, 16), 1),
            (module.date(2026, 9, 17), 4),
        ]
        summary = module.summarize_contributions(days, module.date(2026, 9, 15), module.date(2026, 9, 17))
        self.assertEqual(summary['current_streak'], 2)
        self.assertEqual(summary['longest_streak'], 2)
        self.assertTrue(summary['current_longest_is_ongoing'])

    def test_missing_end_date_is_treated_as_zero_contributions(self):
        days = [
            (module.date(2026, 9, 15), 2),
            (module.date(2026, 9, 16), 1),
        ]
        summary = module.summarize_contributions(days, module.date(2026, 9, 15), module.date(2026, 9, 17))
        self.assertEqual(summary['current_streak'], 0)
        self.assertEqual(summary['days'][-1], (module.date(2026, 9, 17), 0))


class LanguageStatsTests(unittest.TestCase):
    def test_build_language_stats_prefers_requested_primary_language(self):
        primary, share, stats = module.build_language_stats(
            {'Jupyter Notebook': 900, 'Python': 100},
            'Jupyter Notebook',
        )
        self.assertEqual(primary, 'Jupyter Notebook')
        self.assertAlmostEqual(share, 90.0)
        self.assertEqual(stats[0]['name'], 'Jupyter Notebook')

    def test_build_language_stats_falls_back_to_largest_language_when_primary_missing(self):
        primary, share, stats = module.build_language_stats(
            {'Python': 700, 'HTML': 300},
            'Jupyter Notebook',
        )
        self.assertEqual(primary, 'Python')
        self.assertAlmostEqual(share, 70.0)
        self.assertEqual(stats[0]['name'], 'Python')


class ApiHelpersTests(unittest.TestCase):
    def test_elapsed_years_uses_full_anniversary(self):
        self.assertEqual(module.elapsed_years(module.date(2025, 10, 1), module.date(2026, 9, 17)), 0)
        self.assertEqual(module.elapsed_years(module.date(2025, 9, 1), module.date(2026, 9, 17)), 1)

    def test_build_headers_uses_bearer_token(self):
        headers = module.build_headers('abc123', content_type='application/json')
        self.assertEqual(headers['Authorization'], 'Bearer ' + 'abc123')
        self.assertEqual(headers['Content-Type'], 'application/json')


class SvgRenderingTests(unittest.TestCase):
    def test_streak_svg_uses_wider_layout_and_keeps_streak_only_stats(self):
        contrib = {
            'total': 40,
            'current_streak': 3,
            'longest_streak': 7,
            'active_days': 12,
            'peak_day': 5,
            'best_end': module.date(2026, 9, 10),
            'current_longest_is_ongoing': False,
            'range_label': '2025-09-18 → 2026-09-17',
        }
        svg = module.streak_svg(contrib)
        self.assertIn('width="960"', svg)
        self.assertIn('viewBox="0 0 960 400"', svg)
        self.assertIn('40 contributions in the last 365 days', svg)
        self.assertIn('Current streak', svg)
        self.assertIn('Longest streak', svg)
        ET.fromstring(svg)

    def test_activity_svg_uses_wider_layout_and_omits_streak_footer(self):
        contrib = {
            'days': [
                (module.date(2026, 9, 15), 1),
                (module.date(2026, 9, 16), 2),
                (module.date(2026, 9, 17), 0),
            ],
            'current_streak': 0,
            'longest_streak': 2,
            'range_label': '2025-09-18 → 2026-09-17',
        }
        svg = module.activity_svg(contrib)
        self.assertIn('width="960"', svg)
        self.assertIn('viewBox="0 0 960 400"', svg)
        self.assertIn('Daily public contributions', svg)
        self.assertIn(contrib['range_label'], svg)
        self.assertNotIn('Current streak', svg)
        self.assertNotIn('Longest streak', svg)
        ET.fromstring(svg)

    def test_trophies_svg_includes_profile_milestones(self):
        contrib = {
            'total': 40,
            'current_streak': 1,
            'longest_streak': 1,
            'active_days': 4,
            'peak_day': 17,
        }
        profile = {
            'followers': 1,
            'public_repos': 2,
            'total_stars': 0,
            'merged_prs': 3,
            'closed_issues': 0,
            'years_active': 1,
        }
        svg = module.trophies_svg(profile, contrib)
        self.assertIn('Profile Milestones', svg)
        self.assertIn('width="960"', svg)
        self.assertIn('viewBox="0 0 960 320"', svg)
        self.assertIn('Public repos', svg)
        self.assertIn('Followers', svg)
        self.assertIn('Authored PRs', svg)
        self.assertIn('Total stars', svg)
        self.assertIn('Closed issues', svg)
        self.assertIn('Years active', svg)
        self.assertNotIn('Longest streak', svg)
        self.assertNotIn('Active days', svg)
        self.assertNotIn('Current streak', svg)
        ET.fromstring(svg)

    def test_pinned_repos_svg_includes_repository_metadata(self):
        svg = module.pinned_repos_svg(
            [
                {
                    'full_name': 'enricocastrechini/BAC-Mammography-Detection-CVD',
                    'description': 'Deep-learning research exploring breast arterial calcification detection.',
                    'language': 'Jupyter Notebook',
                    'language_breakdown': {'Jupyter Notebook': 900, 'Python': 100},
                    'stargazers_count': 0,
                    'forks_count': 0,
                }
            ]
        )
        self.assertIn('Featured Repositories', svg)
        self.assertIn('width="960"', svg)
        self.assertIn('BAC-Mammography-Detection-CVD', svg)
        self.assertIn('Primary language: Jupyter Notebook • 90.0% of tracked bytes', svg)
        self.assertIn('Python 10.0%', svg)
        self.assertIn('clipPath id="lang-clip-0"', svg)
        ET.fromstring(svg)

    def test_pinned_repos_svg_stacks_multiple_cards_and_grows_height(self):
        repositories = [
            {
                'full_name': 'enricocastrechini/BAC-Mammography-Detection-CVD',
                'description': 'Deep-learning research exploring breast arterial calcification detection.',
                'language': 'Jupyter Notebook',
                'language_breakdown': {'Jupyter Notebook': 900, 'Python': 100},
                'stargazers_count': 0,
                'forks_count': 0,
            },
            {
                'full_name': 'enricocastrechini/enricocastrechini',
                'description': 'This is me.',
                'language': 'Python',
                'language_breakdown': {'Python': 700, 'HTML': 300},
                'stargazers_count': 0,
                'forks_count': 0,
            },
        ]
        svg = module.pinned_repos_svg(repositories)
        self.assertIn('height="630"', svg)
        self.assertIn('viewBox="0 0 960 630"', svg)
        self.assertIn('enricocastrechini/BAC-Mammography-Detection-CVD', svg)
        self.assertIn('enricocastrechini/enricocastrechini', svg)
        ET.fromstring(svg)


if __name__ == '__main__':
    unittest.main()
