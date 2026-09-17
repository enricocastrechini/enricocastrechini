import importlib.util
import pathlib
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / '.github' / 'scripts' / 'generate_github_analytics.py'
spec = importlib.util.spec_from_file_location('generate_github_analytics', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExtractContributionDaysTests(unittest.TestCase):
    def test_extracts_counts_from_day_ids_and_tooltips(self):
        html = '''
        <table>
          <tr>
            <td data-date="2026-09-15" id="contribution-day-component-0-1" class="ContributionCalendar-day"></td>
            <tool-tip for="contribution-day-component-0-1" class="sr-only position-absolute">No contributions on September 15th.</tool-tip>
            <td data-date="2026-09-16" id="contribution-day-component-0-2" class="ContributionCalendar-day"></td>
            <tool-tip for="contribution-day-component-0-2" class="sr-only position-absolute">3 contributions on September 16th.</tool-tip>
            <td data-date="2026-09-17" id="contribution-day-component-0-3" class="ContributionCalendar-day"></td>
            <tool-tip for="contribution-day-component-0-3" class="sr-only position-absolute">1 contribution on September 17th.</tool-tip>
          </tr>
        </table>
        '''
        self.assertEqual(
            module.extract_contribution_days(html),
            [
                (module.date(2026, 9, 15), 0),
                (module.date(2026, 9, 16), 3),
                (module.date(2026, 9, 17), 1),
            ],
        )

    def test_handles_attributes_in_different_order(self):
        html = '''
        <td id="contribution-day-component-0-1" class="ContributionCalendar-day" data-date="2026-09-17"></td>
        <tool-tip class="sr-only position-absolute" for="contribution-day-component-0-1">2 contributions on September 17th.</tool-tip>
        '''
        self.assertEqual(module.extract_contribution_days(html), [(module.date(2026, 9, 17), 2)])

    def test_missing_tooltip_defaults_to_zero(self):
        html = '''
        <td data-date="2026-09-17" id="contribution-day-component-0-1" class="ContributionCalendar-day"></td>
        '''
        self.assertEqual(module.extract_contribution_days(html), [(module.date(2026, 9, 17), 0)])


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


if __name__ == '__main__':
    unittest.main()
