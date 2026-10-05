import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../../../core/api/api_error.dart';
import '../../../core/storage/token_storage.dart';
import '../domain/app_user.dart';

class AuthRepository {
  AuthRepository(this._dio, this._tokens);

  final Dio _dio;
  final TokenStorage _tokens;

  Future<AppUser> login(String login, String password) =>
      _signIn('/auth/login', {'login': login, 'password': password}, login);

  Future<AppUser> pinLogin(String login, String pin) =>
      _signIn('/auth/pin-login', {'login': login, 'pin': pin}, login);

  Future<AppUser> _signIn(
    String path,
    Map<String, dynamic> body,
    String login,
  ) async {
    try {
      final res = await _dio.post(
        path,
        data: body,
        options: Options(extra: {'noAuth': true}),
      );
      await _tokens.save(
        access: res.data['access_token'],
        refresh: res.data['refresh_token'],
        login: login,
      );
      return AppUser.fromJson(res.data['user']);
    } catch (e) {
      throw ApiError.from(e);
    }
  }

  /// Текущий пользователь по сохранённому токену; null — нужен вход.
  Future<AppUser?> restore() async {
    if (await _tokens.accessToken == null) return null;
    try {
      final res = await _dio.get('/auth/me');
      return AppUser.fromJson(res.data);
    } on DioException catch (e) {
      if (e.response?.statusCode == 401) return null;
      rethrow;
    }
  }

  Future<String?> lastLogin() => _tokens.lastLogin;

  Future<void> setShift(bool onShift) async {
    try {
      await _dio.patch('/users/me/shift', data: {'on_shift': onShift});
    } catch (e) {
      throw ApiError.from(e);
    }
  }

  Future<void> registerDevice(String fcmToken) =>
      _dio.post('/auth/me/device', data: {'fcm_token': fcmToken});

  Future<void> logout() => _tokens.clear();
}

final authRepositoryProvider = Provider<AuthRepository>(
  (ref) =>
      AuthRepository(ref.watch(dioProvider), ref.watch(tokenStorageProvider)),
);
