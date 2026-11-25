import unittest

from app import app, db, Admin, Student


class BulkDeleteStudentsTests(unittest.TestCase):
    def setUp(self):
        app.config.update(
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test-secret',
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
            students = [
                Student(
                    username=f'student{number}',
                    password_hash='x',
                    role='student',
                    full_name=f'Student {number}',
                    student_id=f'LIN{number}',
                )
                for number in range(1, 4)
            ]
            db.session.add_all([admin, *students])
            db.session.commit()
            self.admin_id = admin.id
            self.student_ids = [student.id for student in students]

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

    def test_selected_students_are_deleted_and_unselected_students_remain(self):
        response = self.client.post(
            '/admin/students/delete-selected',
            data={'student_ids': [str(self.student_ids[0]), str(self.student_ids[2])]},
        )

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(
                [student.id for student in Student.query.order_by(Student.id).all()],
                [self.student_ids[1]],
            )

    def test_student_list_shows_bulk_selection_controls(self):
        response = self.client.get('/admin/students')

        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('id="select-all-students"', page)
        self.assertIn('name="student_ids"', page)
        self.assertIn('Delete Selected (0)', page)

    def test_empty_or_invalid_selection_deletes_nothing(self):
        for data in ({}, {'student_ids': 'not-an-id'}):
            with self.subTest(data=data):
                response = self.client.post('/admin/students/delete-selected', data=data)
                self.assertEqual(response.status_code, 302)
                with app.app_context():
                    self.assertEqual(Student.query.count(), 3)

    def test_missing_selected_student_prevents_partial_deletion(self):
        response = self.client.post(
            '/admin/students/delete-selected',
            data={'student_ids': [str(self.student_ids[0]), '99999']},
        )

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(Student.query.count(), 3)


if __name__ == '__main__':
    unittest.main()
