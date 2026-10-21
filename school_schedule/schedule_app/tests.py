from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from .services.import_service import (
    day_from_filename,
    parse_schedule_rows,
    read_excel_rows,
)


class ImportServiceTests(SimpleTestCase):
    def test_day_from_filename_supports_russian_and_english(self):
        self.assertEqual(day_from_filename('понедельник.xlsx'), 'monday')
        self.assertEqual(day_from_filename('Tuesday.xls'), 'tuesday')
        self.assertIsNone(day_from_filename('schedule.xlsx'))

    def test_parse_schedule_cell_formats(self):
        rows = [
            ['Понедельник'],
            [None, '5А', '5Б'],
            [1, 'МАТЕМ 12', 'ФИЗ-РА'],
            [2, 'АНГ ЯЗ 11/18', '--'],
            [3, 'ФИЗИКА 8', 'ИСТОРИЯ 4'],
        ]

        parsed = parse_schedule_rows(rows)

        self.assertIn('monday', parsed)
        classes = {item['name']: item for item in parsed['monday']}
        self.assertEqual(classes['5А']['lessons'][0]['subject'], 'МАТЕМ')
        self.assertEqual(
            classes['5А']['lessons'][0]['classrooms'],
            [{'classroom': '12', 'type': ''}],
        )
        self.assertEqual(classes['5Б']['lessons'][0]['subject'], 'ФИЗ-РА')
        self.assertEqual(
            classes['5Б']['lessons'][0]['classrooms'],
            [{'classroom': 'Спортзал', 'type': ''}],
        )
        self.assertEqual(classes['5А']['lessons'][1]['subject'], 'АНГ ЯЗ')
        self.assertEqual(classes['5Б']['lessons'][1]['subject'], '--|--')
        self.assertEqual(classes['5Б']['lessons'][2]['subject'], 'ИСТОРИЯ')

    def test_read_excel_rows_reads_active_sheet(self):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.append(['Понедельник'])
        sheet.append([None, '5А', '5Б'])
        sheet.append([1, 'МАТЕМ 12', 'РУССКИЙ 3'])

        content = BytesIO()
        workbook.save(content)
        upload = SimpleUploadedFile(
            'понедельник.xlsx',
            content.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        rows = read_excel_rows(upload)

        self.assertEqual(rows[0], ['Понедельник', None, None])
        self.assertEqual(rows[1][1:], ['5А', '5Б'])
        self.assertEqual(rows[2][1], 'МАТЕМ 12')
