import 'package:dio/dio.dart';

/// Ошибка API с человекочитаемым текстом (бэкенд отдаёт `detail` на русском).
class ApiError implements Exception {
  ApiError(this.message, {this.statusCode});

  final String message;
  final int? statusCode;

  factory ApiError.from(Object error) {
    if (error is ApiError) return error;
    if (error is DioException) {
      final data = error.response?.data;
      final code = error.response?.statusCode;
      if (data is Map && data['detail'] != null) {
        final detail = data['detail'];
        if (detail is String) return ApiError(detail, statusCode: code);
        if (detail is List && detail.isNotEmpty) {
          final first = detail.first;
          final msg = first is Map
              ? (first['msg'] ?? first.toString())
              : first.toString();
          return ApiError(
            msg.toString().replaceFirst('Value error, ', ''),
            statusCode: code,
          );
        }
      }
      return switch (error.type) {
        DioExceptionType.connectionTimeout ||
        DioExceptionType.receiveTimeout ||
        DioExceptionType.sendTimeout => ApiError(
          'Сервер не отвечает. Проверьте связь.',
        ),
        DioExceptionType.connectionError => ApiError('Нет связи с сервером'),
        _ => ApiError('Ошибка сервера (${code ?? '—'})', statusCode: code),
      };
    }
    return ApiError(error.toString());
  }

  @override
  String toString() => message;
}
