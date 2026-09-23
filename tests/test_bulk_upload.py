import io
import unittest

from app import app, db, Class, User, Admin, Student


class BulkUploadStudentsTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test-secret'
        )
        self.client = app.test_client()

        with app.app_context():
            db.drop_all()
            db.create_all()

            admin = Admin(
                username='admin',
                password_hash='x',
                role='admin',
                is_active=True,
                full_name='Test Admin',
                email='admin@test.local',
            )
            db.session.add(admin)

            class_record = Class(name='JSS 1', level='Junior Secondary', capacity=30, is_active=True)
            db.session.add(class_record)
            db.session.commit()

            self.admin_id = admin.id
            self.class_id = class_record.id

    def _login(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

    @staticmethod
    def _upload(csv_text):
        return io.BytesIO(csv_text.encode('utf-8'))

    def test_upload_creates_students_even_when_class_ignores_spaces_and_case(self):
        self._login()
        csv_text = (
            'First Name,Last Name,Class,Date of Birth,Gender\n'
            'James,Okon,jss1,2012-05-14,Male\n'
        )

        response = self.client.post(
            '/admin/bulk-upload-students',
            data={'file': (self._upload(csv_text), 'students.csv')},
            content_type='multipart/form-data',
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('generated_student_credentials.csv',
                      response.headers.get('Content-Disposition', ''))
        body = response.get_data(as_text=True)
        self.assertIn('Created', body)
        self.assertIn('james.okon', body)

        with app.app_context():
            student = Student.query.filter_by(username='james.okon').first()
            self.assertIsNotNone(student, 'student must be persisted after upload')
            self.assertEqual(student.class_id, self.class_id)
            self.assertEqual(student.full_name, 'James Okon')

    def test_unknown_class_is_skipped_and_reason_is_reported_in_csv(self):
        self._login()
        csv_text = (
            'First Name,Last Name,Class,Date of Birth,Gender\n'
            'Ada,Eze,SS 99,14/05/2012,Female\n'
        )

        response = self.client.post(
            '/admin/bulk-upload-students',
            data={'file': (self._upload(csv_text), 'students.csv')},
            content_type='multipart/form-data',
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        # pandas re-quotes embedded quotes in CSV output, so match the parts.
        self.assertIn('Skipped: Class', body)
        self.assertIn('SS 99', body)
        self.assertIn('does not exist', body)

        with app.app_context():
            self.assertEqual(Student.query.count(), 0)

    def test_summary_banner_appears_on_the_next_page(self):
        self._login()

        # Successful row
        good_csv = (
            'First Name,Last Name,Class,Date of Birth,Gender\n'
            'Ada,Eze,JSS1,14/05/2012,Female\n'
        )
        response = self.client.post(
            '/admin/bulk-upload-students',
            data={'file': (self._upload(good_csv), 'students.csv')},
            content_type='multipart/form-data',
        )
        self.assertEqual(response.status_code, 200)

        page = self.client.get('/admin/students').get_data(as_text=True)
        self.assertIn('1 student(s) created', page)
        self.assertNotIn('were NOT added', page)

        # A row that must be skipped -> red banner on the next page
        bad_csv = (
            'First Name,Last Name,Class,Date of Birth,Gender\n'
            'John,Doe,KG 1,14/05/2012,Male\n'
        )
        response = self.client.post(
            '/admin/bulk-upload-students',
            data={'file': (self._upload(bad_csv), 'students.csv')},
            content_type='multipart/form-data',
        )
        self.assertEqual(response.status_code, 200)

        page = self.client.get('/admin/students').get_data(as_text=True)
        self.assertIn('1 row(s) were NOT added', page)
        self.assertIn('Status column', page)

    def test_duplicate_upload_does_not_duplicate_students(self):
        self._login()
        csv_text = (
            'First Name,Last Name,Class,Date of Birth,Gender\n'
            'James,Okon,JSS 1,2012-05-14,Male\n'
        )
        first = self.client.post(
            '/admin/bulk-upload-students',
            data={'file': (self._upload(csv_text), 'students.csv')},
            content_type='multipart/form-data',
        )
        second = self.client.post(
            '/admin/bulk-upload-students',
            data={'file': (self._upload(csv_text), 'students.csv')},
            content_type='multipart/form-data',
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        # The second upload must not create a duplicate student.
        second_body = second.get_data(as_text=True)
        self.assertIn('already exists', second_body)

        with app.app_context():
            self.assertEqual(Student.query.count(), 1)


if __name__ == '__main__':
    unittest.main()