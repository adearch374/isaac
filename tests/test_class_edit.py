import unittest

from app import app, db, Class, User, generate_password_hash


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


if __name__ == '__main__':
    unittest.main()
