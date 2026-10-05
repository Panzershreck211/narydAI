import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../data/auth_repository.dart';
import '../domain/app_user.dart';

/// Состояние сессии: null — не авторизован.
class AuthController extends AsyncNotifier<AppUser?> {
  AuthRepository get _repo => ref.read(authRepositoryProvider);

  @override
  Future<AppUser?> build() async {
    ref.read(apiClientProvider).onSessionExpired = () =>
        state = const AsyncData(null);
    return _repo.restore();
  }

  Future<void> login(String login, String password) =>
      _run(() => _repo.login(login.trim(), password));

  Future<void> pinLogin(String login, String pin) =>
      _run(() => _repo.pinLogin(login.trim(), pin));

  Future<void> _run(Future<AppUser> Function() action) async {
    state = const AsyncLoading();
    state = await AsyncValue.guard(action);
  }

  Future<void> setShift(bool onShift) async {
    final user = state.asData?.value;
    if (user == null) return;
    await _repo.setShift(onShift);
    state = AsyncData(user.copyWith(onShift: onShift));
  }

  Future<void> logout() async {
    await _repo.logout();
    state = const AsyncData(null);
  }
}

final authControllerProvider = AsyncNotifierProvider<AuthController, AppUser?>(
  AuthController.new,
);

/// Удобный доступ к текущему пользователю (null, пока не вошёл).
final currentUserProvider = Provider<AppUser?>(
  (ref) => ref.watch(authControllerProvider).asData?.value,
);
