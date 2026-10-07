import 'dart:async';
import 'dart:ui';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../i18n/i18n.dart';

/// Системные уведомления. Аварийные наряды — отдельный канал с красным цветом
/// и максимальной важностью (звук, heads-up).
///
/// Сейчас уведомления приходят по WebSocket, пока приложение живо. Для доставки
/// в выгруженное приложение подключается FCM (firebase_messaging): бэкенд уже
/// отправляет push, если задан FCM_CREDENTIALS_FILE, а токен регистрируется
/// через AuthRepository.registerDevice.
class LocalNotifications {
  final _plugin = FlutterLocalNotificationsPlugin();
  final _taps = StreamController<int>.broadcast();

  // Названия каналов видны в настройках телефона — на языке интерфейса
  static AndroidNotificationChannel get _orders => AndroidNotificationChannel(
    'orders',
    tr('Наряды'),
    description: tr('Новые наряды и изменения статусов'),
    importance: Importance.high,
  );
  static AndroidNotificationChannel get _emergency =>
      AndroidNotificationChannel(
        'emergency',
        tr('Аварийные наряды'),
        description: tr('Аварийные наряды и просрочки'),
        importance: Importance.max,
        ledColor: Color(0xFFD32F2F),
        enableLights: true,
      );

  /// id наряда, по уведомлению о котором тапнули.
  Stream<int> get taps => _taps.stream;

  Future<void> init() async {
    await _plugin.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
      onDidReceiveNotificationResponse: (r) {
        final id = int.tryParse(r.payload ?? '');
        if (id != null) _taps.add(id);
      },
    );
    final android = _plugin
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    await android?.createNotificationChannel(_orders);
    await android?.createNotificationChannel(_emergency);
    await android?.requestNotificationsPermission();
  }

  Future<void> show({
    required int id,
    required String title,
    required String body,
    bool emergency = false,
    int? orderId,
  }) {
    final channel = emergency ? _emergency : _orders;
    return _plugin.show(
      id: id,
      title: title,
      body: body,
      payload: orderId?.toString(),
      notificationDetails: NotificationDetails(
        android: AndroidNotificationDetails(
          channel.id,
          channel.name,
          channelDescription: channel.description,
          importance: channel.importance,
          priority: emergency ? Priority.max : Priority.high,
          color: emergency ? const Color(0xFFD32F2F) : const Color(0xFF1565C0),
          colorized: emergency,
          category: emergency
              ? AndroidNotificationCategory.alarm
              : AndroidNotificationCategory.message,
        ),
        iOS: DarwinNotificationDetails(
          interruptionLevel: emergency
              ? InterruptionLevel.timeSensitive
              : InterruptionLevel.active,
        ),
      ),
    );
  }
}

final localNotificationsProvider = Provider<LocalNotifications>(
  (ref) => LocalNotifications(),
);
