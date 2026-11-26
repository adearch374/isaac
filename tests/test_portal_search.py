import unittest

from app import app, db, Admin


class PortalSearchTests(unittest.TestCase):
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
            db.session.add(admin)
            db.session.commit()
            self.admin_id = admin.id

        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin_id)
            session['_fresh'] = True

    def test_shared_search_script_is_loaded(self):
        response = self.client.get('/admin/students')
        self.assertEqual(response.status_code, 200)
        page = response.get_data(as_text=True)
        self.assertIn('/static/portal-search.js', page)

    def test_main_admin_tables_have_search_controls(self):
        routes_and_markers = (
            ('/admin/students', 'student-search'),
            ('/admin/classes', 'Search classes'),
            ('/admin/subjects', 'Search subjects'),
            ('/admin/teachers', 'Search teachers'),
            ('/admin/administrators', 'Search administrators'),
            ('/admin/results', 'Search results'),
            ('/admin/attendance', 'attendance-search'),
            ('/admin/timetable', 'Search timetable'),
            ('/admin/academic-sessions', 'Search sessions'),
            ('/admin/terms', 'Search terms'),
            ('/admin/news', 'Search news'),
            ('/admin/events', 'Search events'),
            ('/admin/gallery', 'Search gallery'),
            ('/admin/messages', 'Search messages'),
            ('/admin/activity-logs', 'activity-search'),
            ('/admin/teacher-requests', 'Search requests'),
        )

        for route, marker in routes_and_markers:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(marker, response.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
