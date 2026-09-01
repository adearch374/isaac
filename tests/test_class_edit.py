import unittest
from unittest.mock import patch

from app import app, db, Class, User, Teacher, Student, generate_password_hash


class ClassEditRouteTests(unittest.TestCase):
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

            admin = User(
                username='admin',
                password_hash=generate_password_hash('secret123'),
                role='admin',
                is_active=True,
                must_change_password=False,
            )
            db.session.add(admin)
            db.session.commit()

            class_record = Class(name='JSS 1', level='Junior Secondary', capacity=30, is_active=True)
            db.session.add(class_record)
            db.session.commit()

            self.class_id = class_record.id
            self.admin_id = admin.id

    def test_edit_class_updates_class_record(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

        response = self.client.post(
            f'/admin/classes/{self.class_id}/edit',
            data={
                'name': 'SS 1',
                'level': 'Senior Secondary',
                'capacity': '45',
                'is_active': 'y',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/classes', response.headers.get('Location', ''))

        with app.app_context():
            updated_class = Class.query.get(self.class_id)
            self.assertEqual(updated_class.name, 'SS 1')
            self.assertEqual(updated_class.level, 'Senior Secondary')
            self.assertEqual(updated_class.capacity, 45)
            self.assertTrue(updated_class.is_active)

    def test_add_subject_logs_without_nested_commit(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

        with patch('app.log_activity') as mock_log_activity:
            response = self.client.post(
                '/admin/subjects/add',
                data={
                    'class_id': str(self.class_id),
                    'name': 'Mathematics',
                    'code': 'MATH',
                    'description': 'Core subject',
                },
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/subjects', response.headers.get('Location', ''))
        mock_log_activity.assert_called_once()
        self.assertEqual(mock_log_activity.call_args.kwargs.get('commit'), False)

    def test_edit_teacher_updates_username(self):
        with app.app_context():
            teacher = Teacher(
                username='teacher1',
                password_hash=generate_password_hash('secret123'),
                role='teacher',
                full_name='John Teacher',
                email='john@example.com',
                phone='12345',
                department='Math',
                qualification='BSc',
                teacher_id='TCH001',
                is_active=True,
                must_change_password=False,
            )
            db.session.add(teacher)
            db.session.commit()
            teacher_id = teacher.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

        response = self.client.post(
            f'/admin/teachers/{teacher_id}/edit',
            data={
                'full_name': 'John Teacher',
                'email': 'john@example.com',
                'phone': '12345',
                'department': 'Math',
                'qualification': 'BSc',
                'username': 'teacher_updated',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/teachers', response.headers.get('Location', ''))

        with app.app_context():
            updated_user = User.query.get(teacher_id)
            self.assertEqual(updated_user.username, 'teacher_updated')

    def test_edit_student_updates_username(self):
        with app.app_context():
            student = Student(
                username='student1',
                password_hash=generate_password_hash('secret123'),
                role='student',
                full_name='Jane Student',
                email='jane@example.com',
                phone='98765',
                student_id='LIN001',
                date_of_birth=None,
                gender='Female',
                address='Main Street',
                parent_name='Parent',
                parent_phone='555',
                class_id=self.class_id,
                is_active=True,
                must_change_password=False,
            )
            db.session.add(student)
            db.session.commit()
            student_id = student.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

        response = self.client.post(
            f'/admin/students/{student_id}/edit',
            data={
                'student_id': 'LIN001',
                'full_name': 'Jane Student',
                'email': 'jane@example.com',
                'phone': '98765',
                'date_of_birth': '',
                'gender': 'Female',
                'address': 'Main Street',
                'parent_name': 'Parent',
                'parent_phone': '555',
                'class_id': str(self.class_id),
                'username': 'student_updated',
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/students', response.headers.get('Location', ''))

        with app.app_context():
            updated_user = User.query.get(student_id)
            self.assertEqual(updated_user.username, 'student_updated')

    def test_submit_teaching_request_handles_missing_teacher_profile(self):
        with app.app_context():
            user = User(
                username='teacher_without_profile',
                password_hash=generate_password_hash('secret123'),
                role='teacher',
                is_active=True,
                must_change_password=False,
            )
            db.session.add(user)
            db.session.commit()
            self.teacher_without_profile_id = user.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.teacher_without_profile_id)
            session['_fresh'] = True

        response = self.client.post(
            '/teacher/submit-request',
            data={'subject_id': '1', 'class_id': str(self.class_id)},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/', response.headers.get('Location', ''))

    def test_site_sets_csp_without_unsafe_eval(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        csp = response.headers.get('Content-Security-Policy', '')
        self.assertIn("script-src", csp)
        self.assertNotIn('unsafe-eval', csp.lower())


if __name__ == '__main__':
    unittest.main()
