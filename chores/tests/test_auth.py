from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.test import TestCase, Client
from django.urls import reverse


class AuthenticationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='testuser@example.com',
            password='SecurePassword123!',
            first_name='Test',
            last_name='User'
        )

    def test_registration_success(self):
        """Guests can successfully register with valid details."""
        url = reverse('register')
        data = {
            'username': 'newuser',
            'email': 'newuser@example.com',
            'first_name': 'New',
            'last_name': 'Member',
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data, follow=True)
        self.assertRedirects(response, reverse('login'))
        self.assertTrue(User.objects.filter(username='newuser').exists())

        new_user = User.objects.get(username='newuser')
        self.assertEqual(new_user.email, 'newuser@example.com')
        self.assertEqual(new_user.first_name, 'New')
        self.assertEqual(new_user.last_name, 'Member')

        # Check flash message
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('created successfully' in str(m) for m in messages))

    def test_registration_duplicate_username(self):
        """Registration fails if username already exists."""
        url = reverse('register')
        data = {
            'username': 'testuser',
            'email': 'another@example.com',
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'username', 'A user with that username already exists.')

    def test_registration_duplicate_email(self):
        """Registration fails if email is already associated with another user."""
        url = reverse('register')
        data = {
            'username': 'uniqueuser',
            'email': 'testuser@example.com',  # Existing email
            'password1': 'StrongPassword789!',
            'password2': 'StrongPassword789!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'email', 'An account with this email address already exists.')

    def test_registration_password_mismatch(self):
        """Registration fails if passwords do not match."""
        url = reverse('register')
        data = {
            'username': 'mismatchuser',
            'email': 'mismatch@example.com',
            'password1': 'PasswordOne123!',
            'password2': 'PasswordTwo123!',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='mismatchuser').exists())

    def test_login_success(self):
        """Users can log in with valid credentials and receive feedback."""
        url = reverse('login')
        response = self.client.post(url, {
            'username': 'testuser',
            'password': 'SecurePassword123!',
        }, follow=True)

        self.assertRedirects(response, reverse('home'))
        self.assertTrue(response.context['user'].is_authenticated)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('Welcome back, testuser' in str(m) for m in messages))

    def test_login_invalid_credentials(self):
        """Login fails with invalid credentials."""
        url = reverse('login')
        response = self.client.post(url, {
            'username': 'testuser',
            'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['user'].is_authenticated)

    def test_logout(self):
        """Users can log out, which terminates session and shows feedback message."""
        self.client.login(username='testuser', password='SecurePassword123!')
        url = reverse('logout')
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, reverse('login'))
        self.assertFalse(response.context['user'].is_authenticated)

        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any('You have been logged out.' in str(m) for m in messages))

    def test_logout_via_get(self):
        """Logout endpoint supports GET request for user convenience."""
        self.client.login(username='testuser', password='SecurePassword123!')
        url = reverse('logout')
        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse('login'))
        self.assertFalse(response.context['user'].is_authenticated)

    def test_authenticated_user_redirected_from_auth_pages(self):
        """Authenticated users visiting login or register are redirected to home."""
        self.client.login(username='testuser', password='SecurePassword123!')

        login_res = self.client.get(reverse('login'))
        self.assertRedirects(login_res, reverse('home'))

        register_res = self.client.get(reverse('register'))
        self.assertRedirects(register_res, reverse('home'))

    def test_unauthenticated_protected_route_redirects_to_login(self):
        """Unauthenticated access to protected routes redirects to login with ?next parameter."""
        dashboard_url = reverse('dashboard')
        response = self.client.get(dashboard_url)
        expected_redirect = f"{reverse('login')}?next={dashboard_url}"
        self.assertRedirects(response, expected_redirect)

    def test_navbar_rendering_authenticated_vs_guest(self):
        """Navbar displays appropriate links based on authentication state."""
        # Guest state
        guest_res = self.client.get(reverse('home'))
        self.assertContains(guest_res, 'Sign In')
        self.assertContains(guest_res, 'Create Account')
        self.assertNotContains(guest_res, 'Sign Out')
        self.assertNotContains(guest_res, 'testuser')

        # Authenticated state
        self.client.login(username='testuser', password='SecurePassword123!')
        auth_res = self.client.get(reverse('home'))
        self.assertContains(auth_res, 'Sign Out')
        self.assertContains(auth_res, 'testuser')
        self.assertContains(auth_res, 'Dashboard')
        self.assertNotContains(auth_res, 'nav-login')
