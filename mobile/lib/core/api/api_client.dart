import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config.dart';
import '../storage/token_storage.dart';

/// Dio с JWT: подставляет access-токен, при 401 один раз обновляет его через
/// refresh-токен и повторяет запрос. Если обновить не удалось — вызывает [onSessionExpired].
class ApiClient {
  ApiClient(this._tokens) {
    dio = Dio(
      BaseOptions(
        baseUrl: '${AppConfig.apiUrl}${AppConfig.apiPrefix}',
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 30),
      ),
    );
    dio.interceptors.add(
      QueuedInterceptorsWrapper(onRequest: _onRequest, onError: _onError),
    );
  }

  final TokenStorage _tokens;
  late final Dio dio;

  /// Устанавливается AuthController-ом: разлогинить пользователя.
  void Function()? onSessionExpired;

  Future<void> _onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await _tokens.accessToken;
    if (token != null && options.extra['noAuth'] != true) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }

  Future<void> _onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final options = err.requestOptions;
    if (err.response?.statusCode != 401 ||
        options.extra['noAuth'] == true ||
        options.extra['retried'] == true) {
      return handler.next(err);
    }
    final refreshed = await _refresh();
    if (!refreshed) {
      onSessionExpired?.call();
      return handler.next(err);
    }
    try {
      options.extra['retried'] = true;
      options.headers['Authorization'] = 'Bearer ${await _tokens.accessToken}';
      handler.resolve(await dio.fetch(options));
    } on DioException catch (e) {
      handler.next(e);
    }
  }

  Future<bool> _refresh() async {
    final refresh = await _tokens.refreshToken;
    if (refresh == null) return false;
    try {
      // Отдельный Dio, чтобы не зациклиться в интерсепторе
      final res = await Dio(
        BaseOptions(baseUrl: dio.options.baseUrl),
      ).post('/auth/refresh', data: {'refresh_token': refresh});
      await _tokens.save(
        access: res.data['access_token'],
        refresh: res.data['refresh_token'],
      );
      return true;
    } on DioException {
      await _tokens.clear();
      return false;
    }
  }
}

final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(ref.watch(tokenStorageProvider)),
);

final dioProvider = Provider<Dio>((ref) => ref.watch(apiClientProvider).dio);
