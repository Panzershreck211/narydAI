import 'package:shared_preferences/shared_preferences.dart';

/// Конфигурация сервера. Адрес по умолчанию задаётся при сборке:
/// flutter run --dart-define=API_URL=http://192.168.1.10:8000
/// Пользователь может сменить его на экране входа («Сервер → Изменить») —
/// так один APK работает и в эмуляторе, и на телефоне в Wi-Fi.
class AppConfig {
  AppConfig._();

  /// 10.0.2.2 — адрес хоста из Android-эмулятора.
  static const defaultApiUrl = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Порт веб-панели: она проксирует /api, /ws и /media, поэтому телефону достаточно его.
  static const panelPort = 8080;

  static const apiPrefix = '/api/v1';

  static const _key = 'server_url';

  /// Текущий адрес сервера: введённый на экране входа, иначе из сборки.
  static String apiUrl = defaultApiUrl;

  static String get wsUrl => '${apiUrl.replaceFirst(RegExp('^http'), 'ws')}/ws';

  static String mediaUrl(String path) =>
      path.startsWith('http') ? path : '$apiUrl$path';

  /// Читает сохранённый адрес. Вызывается в main() до создания клиента API.
  static Future<void> loadServerUrl() async {
    try {
      final saved = await SharedPreferencesAsync().getString(_key);
      if (saved != null && saved.isNotEmpty) apiUrl = saved;
    } catch (_) {
      // хранилище недоступно — остаёмся на адресе из сборки
    }
  }

  /// «192.168.1.5» → «http://192.168.1.5:8080»; пустая строка — адрес из сборки.
  /// Возвращает null, если строка не похожа на адрес сервера.
  static String? normalize(String input) {
    var s = input.trim().replaceAll(RegExp(r'/+$'), '');
    s = s.replaceFirst(RegExp(r'/api(/v1)?$'), '');
    if (s.isEmpty) return defaultApiUrl;
    if (!RegExp(r'^https?://', caseSensitive: false).hasMatch(s)) {
      s = 'http://$s';
    }
    final uri = Uri.tryParse(s);
    if (uri == null || uri.host.isEmpty) return null;
    final withPort = uri.hasPort || uri.scheme == 'https'
        ? uri
        : uri.replace(port: panelPort);
    return withPort.toString().replaceAll(RegExp(r'/+$'), '');
  }

  /// Запоминает адрес на устройстве (адрес из сборки не хранится — к нему можно вернуться).
  static Future<void> saveServerUrl(String url) async {
    apiUrl = url;
    try {
      final prefs = SharedPreferencesAsync();
      if (url == defaultApiUrl) {
        await prefs.remove(_key);
      } else {
        await prefs.setString(_key, url);
      }
    } catch (_) {
      // не сохранилось — адрес действует до перезапуска приложения
    }
  }
}
