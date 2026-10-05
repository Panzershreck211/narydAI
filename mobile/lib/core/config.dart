/// Конфигурация сборки. Переопределяется при запуске:
/// flutter run --dart-define=API_URL=http://192.168.1.10:8000
class AppConfig {
  AppConfig._();

  /// 10.0.2.2 — адрес хоста из Android-эмулятора.
  static const apiUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const apiPrefix = '/api/v1';

  static String get wsUrl => '${apiUrl.replaceFirst(RegExp('^http'), 'ws')}/ws';

  static String mediaUrl(String path) =>
      path.startsWith('http') ? path : '$apiUrl$path';
}
