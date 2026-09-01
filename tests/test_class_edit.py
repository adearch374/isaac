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

    def test_teacher_class_list_and_attendance_are_class_based(self):
        with app.app_context():
            teacher = Teacher(
                username='teacher_class_role',
                password_hash=generate_password_hash('secret123'),
                role='teacher',
                full_name='Class Teacher',
                email='class@example.com',
                phone='12345',
                department='Math',
                qualification='BSc',
                teacher_id='TCHCLASS',
                is_active=True,
                must_change_password=False,
            )
            db.session.add(teacher)
            db.session.commit()

            class_two = Class(name='JSS 2', level='Junior Secondary', capacity=30, is_active=True)
            db.session.add(class_two)
            db.session.commit()

            subject = __import__('app').Subject(
                class_id=self.class_id,
                name='Mathematics',
                code='MATH',
                description='Math',
                is_active=True,
            )
            db.session.add(subject)
            db.session.commit()

            student = Student(
                username='student_for_attendance',
                password_hash=generate_password_hash('secret123'),
                role='student',
                full_name='Student For Attendance',
                email='student_att@example.com',
                phone='123',
                student_id='STDATT001',
                class_id=self.class_id,
                is_active=True,
                must_change_password=False,
            )
            db.session.add(student)
            db.session.commit()

            db.session.add(__import__('app').TeacherSubjectRequest(
                teacher_id=teacher.id,
                subject_id=subject.id,
                class_id=self.class_id,
                status='approved',
            ))
            db.session.commit()
            teacher_id = teacher.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(teacher_id)
            session['_fresh'] = True

        classes_response = self.client.get('/teacher/classes')
        self.assertEqual(classes_response.status_code, 200)
        self.assertIn(b'My Classes', classes_response.data)
        self.assertIn(b'<th>Students</th>', classes_response.data)
        self.assertNotIn(b'<th>Subject</th>', classes_response.data)

        attendance_response = self.client.get('/teacher/attendance')
        self.assertEqual(attendance_response.status_code, 200)
        self.assertIn(b'Attendance', attendance_response.data)
        self.assertIn(b'<th>Students</th>', attendance_response.data)
        self.assertNotIn(b'<th>Subject</th>', attendance_response.data)

        record_response = self.client.post(
            f'/teacher/attendance/{self.class_id}',
            data={
                'student_0': 'present',
                'notes_0': 'On time',
            },
            follow_redirects=False,
        )

        self.assertEqual(record_response.status_code, 302)
        self.assertIn('/teacher/attendance', record_response.headers.get('Location', ''))

        with app.app_context():
            student_id = Student.query.filter_by(username='student_for_attendance').first().id
            teacher_id = Teacher.query.filter_by(username='teacher_class_role').first().id
            attendance_record = __import__('app').Attendance.query.filter_by(
                class_id=self.class_id,
                student_id=student_id,
                recorded_by=teacher_id,
            ).first()
            self.assertIsNotNone(attendance_record)
            self.assertEqual(attendance_record.status, 'present')

    def test_teacher_attendance_history_lists_previous_records(self):
        with app.app_context():
            teacher = Teacher(
                username='teacher_history',
                password_hash=generate_password_hash('secret123'),
                role='teacher',
                full_name='History Teacher',
                email='history@example.com',
                phone='99999',
                department='Science',
                qualification='BSc',
                teacher_id='TCHHIST',
                is_active=True,
                must_change_password=False,
            )
            db.session.add(teacher)
            db.session.commit()

            student = Student(
                username='student_history',
                password_hash=generate_password_hash('secret123'),
                role='student',
                full_name='History Student',
                email='history_student@example.com',
                phone='555',
                student_id='STDHIST001',
                class_id=self.class_id,
                is_active=True,
                must_change_password=False,
            )
            db.session.add(student)
            db.session.commit()

            subject = __import__('app').Subject(
                class_id=self.class_id,
                name='Biology',
                code='BIO',
                description='Biology',
                is_active=True,
            )
            db.session.add(subject)
            db.session.commit()

            db.session.add(__import__('app').TeacherSubjectRequest(
                teacher_id=teacher.id,
                subject_id=subject.id,
                class_id=self.class_id,
                status='approved',
            ))
            db.session.commit()

            attendance_date = __import__('datetime').date(2026, 9, 1)
            db.session.add(__import__('app').Attendance(
                student_id=student.id,
                class_id=self.class_id,
                date=attendance_date,
                status='present',
                notes='On time',
                recorded_by=teacher.id,
            ))
            db.session.commit()
            teacher_id = teacher.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(teacher_id)
            session['_fresh'] = True

        response = self.client.get('/teacher/attendance')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Attendance History', response.data)
        self.assertIn(b'History Student', response.data)
        self.assertIn(b'present', response.data.lower())

    def test_teacher_can_submit_multiple_subject_requests(self):
        with app.app_context():
            teacher = Teacher(
                username='teacher_multi_subject',
                password_hash=generate_password_hash('secret123'),
                role='teacher',
                full_name='Multi Subject Teacher',
                email='multi@example.com',
                phone='123',
                department='English',
                qualification='BA',
                teacher_id='TCHMULTI',
                is_active=True,
                must_change_password=False,
            )
            db.session.add(teacher)
            db.session.commit()

            maths = __import__('app').Subject(
                class_id=self.class_id,
                name='Mathematics',
                code='MATH2',
                description='Math',
                is_active=True,
            )
            english = __import__('app').Subject(
                class_id=self.class_id,
                name='English',
                code='ENG2',
                description='English',
                is_active=True,
            )
            db.session.add_all([maths, english])
            db.session.commit()
            maths_id = maths.id
            english_id = english.id
            teacher_id = teacher.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(teacher_id)
            session['_fresh'] = True

        response = self.client.post(
            '/teacher/submit-request',
            data={'subject_ids': [str(maths_id), str(english_id)], 'class_id': str(self.class_id)},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/teacher/requests', response.headers.get('Location', ''))

        with app.app_context():
            request_count = __import__('app').TeacherSubjectRequest.query.filter_by(teacher_id=teacher_id).count()
            self.assertEqual(request_count, 2)

    def test_student_results_page_renders_approved_results(self):
        with app.app_context():
            teacher = Teacher(
                username='teacher_results_view',
                password_hash=generate_password_hash('secret123'),
                role='teacher',
                full_name='Results Teacher',
                email='results_teacher@example.com',
                phone='111',
                department='Math',
                qualification='BSc',
                teacher_id='TCHRESULTS',
                is_active=True,
                must_change_password=False,
            )
            db.session.add(teacher)
            db.session.commit()

            student = Student(
                username='student_results_view',
                password_hash=generate_password_hash('secret123'),
                role='student',
                full_name='Results Student',
                email='results_student@example.com',
                phone='222',
                student_id='STDRESULTS001',
                class_id=self.class_id,
                is_active=True,
                must_change_password=False,
            )
            db.session.add(student)
            db.session.commit()

            subject = __import__('app').Subject(
                class_id=self.class_id,
                name='Mathematics',
                code='MATH3',
                description='Math',
                is_active=True,
            )
            db.session.add(subject)
            db.session.commit()

            session_record = __import__('app').AcademicSession(
                name='2026/2027',
                start_date=__import__('datetime').date(2026, 9, 1),
                end_date=__import__('datetime').date(2027, 7, 31),
                is_active=True,
            )
            db.session.add(session_record)
            db.session.commit()

            term = __import__('app').Term(
                name='First Term',
                session_id=session_record.id,
                start_date=__import__('datetime').date(2026, 9, 1),
                end_date=__import__('datetime').date(2026, 12, 20),
                is_active=True,
            )
            db.session.add(term)
            db.session.commit()

            db.session.add(__import__('app').Result(
                student_id=student.id,
                subject_id=subject.id,
                class_id=self.class_id,
                teacher_id=teacher.id,
                term_id=term.id,
                session_id=session_record.id,
                ca_score=70.0,
                exam_score=80.0,
                total_score=150.0,
                grade='A',
                remark='Excellent',
                status='approved',
                created_at=__import__('datetime').datetime.utcnow(),
            ))
            db.session.commit()
            student_id = student.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(student_id)
            session['_fresh'] = True

        response = self.client.get('/student/my-results')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'My Results', response.data)
        self.assertIn(b'Mathematics', response.data)
        self.assertIn(b'Approved', response.data)

    def test_student_can_select_many_subjects_from_own_class_only(self):
        with app.app_context():
            student = Student(
                username='student_subject_choice',
                password_hash=generate_password_hash('secret123'),
                role='student',
                full_name='Subject Choice Student',
                email='choice@example.com',
                phone='555',
                student_id='STDSELECT001',
                class_id=self.class_id,
                is_active=True,
                must_change_password=False,
            )
            db.session.add(student)
            db.session.commit()

            other_class = __import__('app').Class(name='SS 1', level='Senior Secondary', capacity=30, is_active=True)
            db.session.add(other_class)
            db.session.commit()

            same_class_subject = __import__('app').Subject(
                class_id=self.class_id,
                name='Science',
                code='SCI',
                description='Science',
                is_active=True,
            )
            same_class_subject_two = __import__('app').Subject(
                class_id=self.class_id,
                name='Commerce',
                code='COM',
                description='Commerce',
                is_active=True,
            )
            other_class_subject = __import__('app').Subject(
                class_id=other_class.id,
                name='Art',
                code='ART',
                description='Art',
                is_active=True,
            )
            db.session.add_all([same_class_subject, same_class_subject_two, other_class_subject])
            db.session.commit()
            same_class_subject_id = same_class_subject.id
            same_class_subject_two_id = same_class_subject_two.id
            other_class_subject_id = other_class_subject.id
            student_id = student.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(student_id)
            session['_fresh'] = True

        invalid_response = self.client.post(
            '/student/subjects/select',
            data={'subject_ids': [str(same_class_subject_id), str(other_class_subject_id)]},
            follow_redirects=False,
        )
        self.assertEqual(invalid_response.status_code, 302)
        self.assertIn('/student/subjects', invalid_response.headers.get('Location', ''))

        valid_response = self.client.post(
            '/student/subjects/select',
            data={'subject_ids': [str(same_class_subject_id), str(same_class_subject_two_id)]},
            follow_redirects=False,
        )
        self.assertEqual(valid_response.status_code, 302)
        self.assertIn('/student/subjects', valid_response.headers.get('Location', ''))

        with app.app_context():
            choices = __import__('app').StudentSubjectChoice.query.filter_by(student_id=student_id).order_by(__import__('app').StudentSubjectChoice.subject_id).all()
            self.assertEqual(len(choices), 2)
            self.assertEqual({choice.subject_id for choice in choices}, {same_class_subject_id, same_class_subject_two_id})
            self.assertTrue(all(choice.class_id == self.class_id for choice in choices))

    def test_student_dashboard_shows_selected_subject_count(self):
        with app.app_context():
            student = Student(
                username='student_dashboard_subject_count',
                password_hash=generate_password_hash('secret123'),
                role='student',
                full_name='Dashboard Subject Student',
                email='dashboard_subject@example.com',
                phone='777',
                student_id='STDDASH001',
                class_id=self.class_id,
                is_active=True,
                must_change_password=False,
            )
            db.session.add(student)
            db.session.commit()

            subjects = [
                __import__('app').Subject(class_id=self.class_id, name='Physics', code='PHY', description='Physics', is_active=True),
                __import__('app').Subject(class_id=self.class_id, name='Chemistry', code='CHE', description='Chemistry', is_active=True),
            ]
            db.session.add_all(subjects)
            db.session.commit()

            db.session.add_all([
                __import__('app').StudentSubjectChoice(student_id=student.id, subject_id=subjects[0].id, class_id=self.class_id),
                __import__('app').StudentSubjectChoice(student_id=student.id, subject_id=subjects[1].id, class_id=self.class_id),
            ])
            db.session.commit()
            student_id = student.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(student_id)
            session['_fresh'] = True

        response = self.client.get('/student/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<h3>2</h3>', response.data)
        self.assertIn(b'Subjects', response.data)

    def test_student_repeated_save_cleans_duplicate_rows_before_commit(self):
        with app.app_context():
            student = Student(
                username='student_duplicate_cleanup',
                password_hash=generate_password_hash('secret123'),
                role='student',
                full_name='Duplicate Cleanup Student',
                email='duplicate_cleanup@example.com',
                phone='888',
                student_id='STDDUP001',
                class_id=self.class_id,
                is_active=True,
                must_change_password=False,
            )
            db.session.add(student)
            db.session.commit()

            subject = __import__('app').Subject(
                class_id=self.class_id,
                name='Agriculture',
                code='AGR',
                description='Agriculture',
                is_active=True,
            )
            db.session.add(subject)
            db.session.commit()

            db.session.execute(__import__('app').text('DROP TABLE IF EXISTS student_subject_choice'))
            db.session.execute(__import__('app').text('''
                CREATE TABLE student_subject_choice (
                    id INTEGER NOT NULL PRIMARY KEY,
                    student_id INTEGER NOT NULL,
                    subject_id INTEGER NOT NULL,
                    class_id INTEGER NOT NULL,
                    selected_at DATETIME,
                    updated_at DATETIME,
                    FOREIGN KEY (student_id) REFERENCES student (id),
                    FOREIGN KEY (subject_id) REFERENCES subject (id),
                    FOREIGN KEY (class_id) REFERENCES class (id)
                )
            '''))
            subject_id = subject.id
            db.session.execute(__import__('app').text('''
                INSERT INTO student_subject_choice (student_id, subject_id, class_id) VALUES (:student_id, :subject_id, :class_id)
            '''), {'student_id': student.id, 'subject_id': subject_id, 'class_id': self.class_id})
            db.session.execute(__import__('app').text('''
                INSERT INTO student_subject_choice (student_id, subject_id, class_id) VALUES (:student_id, :subject_id, :class_id)
            '''), {'student_id': student.id, 'subject_id': subject_id, 'class_id': self.class_id})
            db.session.commit()
            student_id = student.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(student_id)
            session['_fresh'] = True

        response = self.client.post(
            '/student/subjects/select',
            data={'subject_ids': [str(subject_id)]},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn('/student/subjects', response.headers.get('Location', ''))

        with app.app_context():
            choices = __import__('app').StudentSubjectChoice.query.filter_by(student_id=student_id, subject_id=subject_id).all()
            self.assertEqual(len(choices), 1)

    def test_site_sets_csp_without_unsafe_eval(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        csp = response.headers.get('Content-Security-Policy', '')
        self.assertIn("script-src", csp)
        self.assertNotIn('unsafe-eval', csp.lower())


if __name__ == '__main__':
    unittest.main()
