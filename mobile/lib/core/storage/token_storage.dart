import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// JWT-токены хранятся в Keystore/Keychain, а не в SharedPreferences.
class TokenStorage {
  TokenStorage([FlutterSecureStorage? storage])
    : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  static const _access = 'access_token';
  static const _refresh = 'refresh_token';
  static const _lastLogin = 'last_login';

  String? _cachedAccess;

  Future<String?> get accessToken async =>
      _cachedAccess ??= await _storage.read(key: _access);

  Future<String?> get refreshToken => _storage.read(key: _refresh);

  /// Табельный номер последнего входа — чтобы рабочему вводить только ПИН.
  Future<String?> get lastLogin => _storage.read(key: _lastLogin);

  Future<void> save({
    required String access,
    required String refresh,
    String? login,
  }) async {
    _cachedAccess = access;
    await _storage.write(key: _access, value: access);
    await _storage.write(key: _refresh, value: refresh);
    if (login != null) await _storage.write(key: _lastLogin, value: login);
  }

  Future<void> clear() async {
    _cachedAccess = null;
    await _storage.delete(key: _access);
    await _storage.delete(key: _refresh);
  }
}

final tokenStorageProvider = Provider<TokenStorage>((ref) => TokenStorage());
