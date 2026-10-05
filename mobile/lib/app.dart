import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/notifications/local_notifications.dart';
import 'core/realtime/realtime_service.dart';
import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';

class NaryadApp extends ConsumerStatefulWidget {
  const NaryadApp({super.key});

  @override
  ConsumerState<NaryadApp> createState() => _NaryadAppState();
}

class _NaryadAppState extends ConsumerState<NaryadApp> {
  StreamSubscription<int>? _taps;

  @override
  void initState() {
    super.initState();
    // Тап по системному уведомлению открывает наряд
    _taps = ref
        .read(localNotificationsProvider)
        .taps
        .listen((orderId) => ref.read(routerProvider).push('/orders/$orderId'));
  }

  @override
  void dispose() {
    _taps?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Держим WebSocket открытым, пока пользователь в системе
    ref.watch(realtimeServiceProvider);

    return MaterialApp.router(
      title: 'НарядAI',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: AppTheme.mode,
      routerConfig: ref.watch(routerProvider),
      locale: const Locale('ru'),
      supportedLocales: const [Locale('ru'), Locale('kk'), Locale('en')],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
    );
  }
}
