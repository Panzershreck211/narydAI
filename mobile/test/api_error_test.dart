import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naryad_ai/core/api/api_error.dart';
import 'package:naryad_ai/features/auth/domain/app_user.dart';

DioException _http(int code, Object? data) {
  final req = RequestOptions(path: '/x');
  return DioException(
    requestOptions: req,
    type: DioExceptionType.badResponse,
    response: Response(requestOptions: req, statusCode: code, data: data),
  );
}

void main() {
  group('ApiError.from', () {
    test('detail-строка бэкенда', () {
      final e = ApiError.from(
        _http(409, {'detail': 'Сначала приостановите наряд НР-1'}),
      );
      expect(e.message, 'Сначала приостановите наряд НР-1');
      expect(e.statusCode, 409);
    });

    test('ошибка валидации FastAPI (список)', () {
      final e = ApiError.from(
        _http(422, {
          'detail': [
            {
              'loc': ['body', 'pin'],
              'msg': 'Value error, ПИН из 4–6 цифр',
            },
          ],
        }),
      );
      expect(e.message, 'ПИН из 4–6 цифр');
    });

    test('нет сети и таймаут', () {
      final req = RequestOptions(path: '/x');
      expect(
        ApiError.from(
          DioException(
            requestOptions: req,
            type: DioExceptionType.connectionError,
          ),
        ).message,
        'Нет связи с сервером',
      );
      expect(
        ApiError.from(
          DioException(
            requestOptions: req,
            type: DioExceptionType.receiveTimeout,
          ),
        ).message,
        contains('не отвечает'),
      );
    });

    test('ответ без detail', () {
      expect(
        ApiError.from(_http(500, 'Internal Server Error')).message,
        'Ошибка сервера (500)',
      );
    });

    test('ApiError не оборачивается повторно', () {
      final original = ApiError('x', statusCode: 403);
      expect(identical(ApiError.from(original), original), isTrue);
    });
  });

  group('AppUser', () {
    test('парсинг и короткое имя', () {
      final u = AppUser.fromJson({
        'id': 4,
        'login': '1001',
        'fio': 'Иванов Сергей Николаевич',
        'role': 'executor',
        'specialty': 'Слесарь-ремонтник',
        'grade': 5,
        'brigade_id': 1,
        'on_shift': true,
        'has_pin': true,
      });
      expect(u.role, Role.executor);
      expect(u.shortName, 'Иванов С.Н.');
      expect(u.copyWith(onShift: false).onShift, isFalse);
      expect(u.copyWith(onShift: false).fio, u.fio);
    });

    test('короткое имя для неполного ФИО', () {
      final u = AppUser.fromJson({
        'id': 1,
        'login': 'a',
        'fio': 'Администратор',
        'role': 'admin',
      });
      expect(u.shortName, 'Администратор');
    });
  });
}
