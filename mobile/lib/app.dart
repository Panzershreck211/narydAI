import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/i18n/i18n.dart';
import 'core/notifications/local_notifications.dart';
import 'core/realtime/realtime_service.dart';
import 'core/router/app_router.dart';
import 'core/theme/app_theme.dart';
import 'features/notifications/presentation/notifications_screen.dart';
import 'features/orders/application/orders_providers.dart';

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
    final lang = ref.watch(langProvider);
    // Сервер отдаёт свои тексты на языке запроса — после смены языка перезапрашиваем данные
    // и переподключаем WebSocket (в нём уведомления тоже переводятся).
    ref.listen(langProvider, (_, _) {
      ref.invalidate(myOrdersProvider);
      ref.invalidate(orderDetailProvider);
      ref.invalidate(notificationsProvider);
      ref.invalidate(realtimeServiceProvider);
    });

    return MaterialApp.router(
      title: 'НарядAI',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: AppTheme.mode,
      routerConfig: ref.watch(routerProvider),
      locale: lang.locale,
      supportedLocales: [for (final l in AppLang.values) l.locale],
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      // tr() читает язык при построении: при смене языка routerProvider создаёт новый
      // роутер, и все экраны строятся заново (см. app_router.dart)
    );
  }
}
