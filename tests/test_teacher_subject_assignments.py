import unittest

from app import app, db, Admin, Class, Subject, Teacher, TeacherSubjectRequest


class TeacherSubjectAssignmentsTests(unittest.TestCase):
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
            teacher = Teacher(
                username='teacher',
                password_hash='x',
                role='teacher',
                full_name='Test Teacher',
                teacher_id='TCH001',
                email='teacher@test.local',
            )
            school_class = Class(name='JSS 1', is_active=True)
            db.session.add_all([admin, teacher, school_class])
            db.session.flush()
            subject = Subject(
                name='Mathematics',
                code='MTH1',
                class_id=school_class.id,
                is_active=True,
            )
            db.session.add(subject)
            db.session.commit()
            self.admin_id = admin.id
            self.teacher_id = teacher.id
            self.subject_id = subject.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

    def test_admin_can_assign_subject_and_teacher_sees_assignment(self):
        response = self.client.post(
            f'/admin/teachers/{self.teacher_id}/subjects',
            data={'subject_id': str(self.subject_id)},
        )

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            assignment = TeacherSubjectRequest.query.one()
            self.assertEqual(assignment.teacher_id, self.teacher_id)
            self.assertEqual(assignment.subject_id, self.subject_id)
            self.assertEqual(assignment.status, 'approved')

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.teacher_id)
            session['_fresh'] = True
        teacher_page = self.client.get('/teacher/subjects')
        self.assertEqual(teacher_page.status_code, 200)
        self.assertIn(b'Mathematics', teacher_page.data)

    def test_admin_can_remove_assignment_and_teacher_loses_access(self):
        with app.app_context():
            assignment = TeacherSubjectRequest(
                teacher_id=self.teacher_id,
                subject_id=self.subject_id,
                class_id=db.session.get(Subject, self.subject_id).class_id,
                status='approved',
            )
            db.session.add(assignment)
            db.session.commit()
            assignment_id = assignment.id

        response = self.client.post(
            f'/admin/teachers/{self.teacher_id}/subjects/{assignment_id}/remove'
        )

        self.assertEqual(response.status_code, 302)
        with app.app_context():
            assignment = db.session.get(TeacherSubjectRequest, assignment_id)
            self.assertEqual(assignment.status, 'rejected')

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.teacher_id)
            session['_fresh'] = True
        teacher_page = self.client.get('/teacher/subjects')
        self.assertEqual(teacher_page.status_code, 200)
        self.assertIn(b'No Assigned Subjects', teacher_page.data)

    def test_rejects_inactive_or_invalid_subject(self):
        response = self.client.post(
            f'/admin/teachers/{self.teacher_id}/subjects',
            data={'subject_id': 'not-an-id'},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertEqual(TeacherSubjectRequest.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
