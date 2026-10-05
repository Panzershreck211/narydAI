import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

import '../../features/auth/application/auth_controller.dart';
import '../config.dart';
import '../notifications/local_notifications.dart';
import '../storage/token_storage.dart';

sealed class RealtimeEvent {
  const RealtimeEvent();

  static RealtimeEvent? parse(Map<String, dynamic> j) => switch (j['type']) {
    'order_changed' => OrderChanged(
      j['order_id'] as int,
      j['status'] as String,
    ),
    'notification' => NotificationReceived(
      Map<String, dynamic>.from(j['notification']),
    ),
    _ => null,
  };
}

class OrderChanged extends RealtimeEvent {
  const OrderChanged(this.orderId, this.status);
  final int orderId;
  final String status;
}

class NotificationReceived extends RealtimeEvent {
  const NotificationReceived(this.data);
  final Map<String, dynamic> data;

  int? get orderId => data['order_id'] as int?;
  bool get isEmergency => data['is_emergency'] == true;
}

/// WebSocket с автопереподключением (экспоненциальная задержка до 30 с) и ping каждые 25 с.
class RealtimeService {
  RealtimeService(this._tokens);

  final TokenStorage _tokens;
  final _events = StreamController<RealtimeEvent>.broadcast();
  WebSocketChannel? _channel;
  StreamSubscription? _sub;
  Timer? _ping;
  Timer? _reconnect;
  int _attempt = 0;
  bool _active = false;

  Stream<RealtimeEvent> get events => _events.stream;

  Future<void> start() async {
    if (_active) return;
    _active = true;
    await _connect();
  }

  Future<void> _connect() async {
    final token = await _tokens.accessToken;
    if (!_active || token == null) return;
    try {
      final channel = WebSocketChannel.connect(
        Uri.parse('${AppConfig.wsUrl}?token=$token'),
      );
      await channel.ready;
      _channel = channel;
      _attempt = 0;
      _sub = channel.stream.listen(
        _onMessage,
        onDone: _scheduleReconnect,
        onError: (_) => _scheduleReconnect(),
      );
      _ping = Timer.periodic(
        const Duration(seconds: 25),
        (_) => _channel?.sink.add('ping'),
      );
    } catch (e) {
      debugPrint('WS connect failed: $e');
      _scheduleReconnect();
    }
  }

  void _onMessage(dynamic raw) {
    try {
      final event = RealtimeEvent.parse(
        jsonDecode(raw as String) as Map<String, dynamic>,
      );
      if (event != null) _events.add(event);
    } catch (e) {
      debugPrint('WS bad message: $e');
    }
  }

  void _scheduleReconnect() {
    _cleanup();
    if (!_active) return;
    final delay = Duration(seconds: min(30, pow(2, _attempt++).toInt()));
    _reconnect = Timer(delay, _connect);
  }

  void _cleanup() {
    _ping?.cancel();
    _reconnect?.cancel();
    _sub?.cancel();
    _channel?.sink.close();
    _channel = null;
  }

  void stop() {
    _active = false;
    _cleanup();
  }

  void dispose() {
    stop();
    _events.close();
  }
}

/// Живёт, пока пользователь авторизован; при выходе соединение закрывается.
final realtimeServiceProvider = Provider<RealtimeService?>((ref) {
  // select по id: смена флага «на смене» не должна переподключать сокет
  final userId = ref.watch(currentUserProvider.select((u) => u?.id));
  if (userId == null) return null;

  final service = RealtimeService(ref.read(tokenStorageProvider))..start();
  final notifications = ref.read(localNotificationsProvider);
  final sub = service.events.listen((e) {
    if (e is NotificationReceived) {
      notifications.show(
        id: e.data['id'] as int,
        title: e.data['title'] as String,
        body: e.data['body'] as String,
        emergency: e.isEmergency,
        orderId: e.orderId,
      );
    }
  });
  ref.onDispose(() {
    sub.cancel();
    service.dispose();
  });
  return service;
});

final realtimeEventsProvider = StreamProvider<RealtimeEvent>((ref) {
  final service = ref.watch(realtimeServiceProvider);
  return service?.events ?? const Stream.empty();
});
