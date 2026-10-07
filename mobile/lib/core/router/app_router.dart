import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/assistant/presentation/assistant_screen.dart';
import '../../features/auth/application/auth_controller.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/notifications/presentation/notifications_screen.dart';
import '../../features/orders/presentation/close_order_screen.dart';
import '../../features/orders/presentation/my_orders_screen.dart';
import '../../features/orders/presentation/order_detail_screen.dart';
import '../i18n/i18n.dart';

/// Приложение — только для исполнителей: мастер, руководитель и администратор работают в веб-панели.
bool _allowed(String path) =>
    path.startsWith('/orders') ||
    path.startsWith('/notifications') ||
    path == '/assistant';

final routerProvider = Provider<GoRouter>((ref) {
  // Смена языка — новый роутер, и все экраны строятся заново. Иначе навигатор (у него
  // GlobalKey) переносится в дерево целиком, и неизменяемые (const) виджеты вроде кнопки
  // «Помощник» остаются на прежнем языке. Язык меняют только на корневых экранах
  // (вход, «Мои наряды»), так что начать с /splash → redirect ничего не теряет.
  ref.watch(langProvider);

  // Мост Riverpod → GoRouter: пересчитывать redirect при смене сессии
  final refresh = ValueNotifier(0);
  ref.listen(authControllerProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  final router = GoRouter(
    initialLocation: '/splash',
    refreshListenable: refresh,
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final path = state.matchedLocation;
      final user = auth.asData?.value;

      if (auth.isLoading && !auth.hasValue) {
        return path == '/splash' ? null : '/splash';
      }
      if (user == null) return path == '/login' ? null : '/login';
      if (path == '/login' || path == '/splash') return '/orders';
      return _allowed(path) ? null : '/orders';
    },
    routes: [
      GoRoute(
        path: '/splash',
        builder: (_, _) =>
            const Scaffold(body: Center(child: CircularProgressIndicator())),
      ),
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/orders', builder: (_, _) => const MyOrdersScreen()),
      GoRoute(
        path: '/orders/:id',
        builder: (_, s) =>
            OrderDetailScreen(orderId: int.parse(s.pathParameters['id']!)),
        routes: [
          GoRoute(
            path: 'close',
            builder: (_, s) =>
                CloseOrderScreen(orderId: int.parse(s.pathParameters['id']!)),
          ),
        ],
      ),
      GoRoute(
        path: '/notifications',
        builder: (_, _) => const NotificationsScreen(),
      ),
      GoRoute(path: '/assistant', builder: (_, _) => const AssistantScreen()),
    ],
  );
  ref.onDispose(router.dispose);
  return router;
});
