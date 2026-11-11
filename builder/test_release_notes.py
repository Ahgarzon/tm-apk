import json
import unittest
from release_notes import notification_summary


class ReleaseNotesTests(unittest.TestCase):
    source = 'a' * 40

    def notes(self, changes=None):
        return {'schema': 1, 'application': 'TourMaps GO+',
                'sources': {self.source: changes or ['GPS de carguero cada 1 m', 'Nueva portada de la Junta']}}

    def test_reviewed_changes_are_carried_into_existing_sender_field(self):
        self.assertEqual(notification_summary(json.dumps(self.notes()), self.source),
                         'GPS de carguero cada 1 m; Nueva portada de la Junta')

    def test_previous_source_notes_cannot_describe_new_source(self):
        with self.assertRaises(ValueError):
            notification_summary(json.dumps(self.notes()), 'b' * 40)

    def test_template_rejects_generic_missing_control_url_and_excess_text(self):
        cases = [[], ['cambios integrados del equipo'], ['GPS actualizado\nOtra línea'],
                 ['Consultar https://example.com'], ['x' * 181], ['x' * 180] * 4, [123]]
        for changes in cases:
            data = self.notes(); data['sources'][self.source] = changes
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                notification_summary(json.dumps(data), self.source)

    def test_wrong_schema_and_oversized_data_fail_closed(self):
        for data in [{}, {'schema': True, 'application': 'TourMaps GO+', 'sources': {}}]:
            with self.assertRaises(ValueError):
                notification_summary(json.dumps(data), self.source)
        with self.assertRaises(ValueError):
            notification_summary(' ' * 262145, self.source)


if __name__ == '__main__':
    unittest.main()
