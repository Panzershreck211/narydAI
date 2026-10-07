import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naryad_ai/core/api/api_error.dart';
import 'package:naryad_ai/features/auth/application/auth_controller.dart';
import 'package:naryad_ai/features/auth/data/auth_repository.dart';
import 'package:naryad_ai/features/auth/domain/app_user.dart';

AppUser _user(String role) => AppUser.fromJson({
  'id': 7,
  'login': role,
  'fio': 'Тестов Тест',
  'role': role,
});

/// Сервер «пускает» любого — запрет для не-исполнителей делает само приложение.
class _FakeAuth implements AuthRepository {
  _FakeAuth({this.stored});
  final AppUser? stored;
  var loggedOut = false;

  @override
  Future<AppUser> login(String login, String password) async => _user(login);

  @override
  Future<AppUser> pinLogin(String login, String pin) async => _user(login);

  @override
  Future<AppUser?> restore() async => stored;

  @override
  Future<void> logout() async => loggedOut = true;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

ProviderContainer _container(_FakeAuth repo) => ProviderContainer(
  overrides: [authRepositoryProvider.overrideWithValue(repo)],
);

void main() {
  test('исполнитель входит в приложение', () async {
    final c = _container(_FakeAuth());
    await c.read(authControllerProvider.future);
    await c.read(authControllerProvider.notifier).login('executor', 'x');
    expect(c.read(currentUserProvider)?.role, Role.executor);
  });

  for (final role in ['master', 'manager', 'admin']) {
    test('$role не входит — приложение только для исполнителей', () async {
      final repo = _FakeAuth();
      final c = _container(repo);
      await c.read(authControllerProvider.future);
      await c.read(authControllerProvider.notifier).login(role, 'x');

      final state = c.read(authControllerProvider);
      expect(state.hasError, isTrue);
      expect(ApiError.from(state.error!).message, contains('веб-панели'));
      expect(repo.loggedOut, isTrue); // токены мастера не остаются в телефоне
    });
  }

  test('сохранённая сессия мастера сбрасывается при запуске', () async {
    final repo = _FakeAuth(stored: _user('master'));
    final c = _container(repo);
    expect(await c.read(authControllerProvider.future), isNull);
    expect(repo.loggedOut, isTrue);
  });
}
