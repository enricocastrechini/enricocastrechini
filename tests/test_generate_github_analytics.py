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

    def test_missing_tooltip_defaults_to_zero(self):
        html = '''
        <td data-date="2026-09-17" id="contribution-day-component-0-1" class="ContributionCalendar-day"></td>
        '''
        self.assertEqual(module.extract_contribution_days(html), [(module.date(2026, 9, 17), 0)])


if __name__ == '__main__':
    unittest.main()
