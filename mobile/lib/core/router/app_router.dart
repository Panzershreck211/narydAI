import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/admin/presentation/admin_screen.dart';
import '../../features/auth/application/auth_controller.dart';
import '../../features/auth/domain/app_user.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/manager/presentation/analytics_screen.dart';
import '../../features/master/presentation/board_screen.dart';
import '../../features/master/presentation/create_order_screen.dart';
import '../../features/notifications/presentation/notifications_screen.dart';
import '../../features/orders/presentation/close_order_screen.dart';
import '../../features/orders/presentation/my_orders_screen.dart';
import '../../features/orders/presentation/order_detail_screen.dart';

/// Стартовый экран для роли.
String homeFor(Role role) => switch (role) {
  Role.executor => '/orders',
  Role.master => '/board',
  Role.manager => '/analytics',
  Role.admin => '/admin',
};

/// Какие разделы доступны роли (дублирует RBAC бэкенда на уровне UI).
bool _allowed(Role role, String path) {
  if (path.startsWith('/notifications')) return true;
  if (RegExp(r'^/orders/\d+$').hasMatch(path)) {
    return true; // карточка — всем, права проверит API
  }
  return switch (role) {
    Role.executor => path.startsWith('/orders'),
    Role.master => path.startsWith('/board'),
    Role.manager => path.startsWith('/analytics'),
    Role.admin => path.startsWith('/admin'),
  };
}

final routerProvider = Provider<GoRouter>((ref) {
  // Мост Riverpod → GoRouter: пересчитывать redirect при смене сессии
  final refresh = ValueNotifier(0);
  ref.listen(authControllerProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
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
      if (path == '/login' || path == '/splash') return homeFor(user.role);
      return _allowed(user.role, path) ? null : homeFor(user.role);
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
        path: '/board',
        builder: (_, _) => const BoardScreen(),
        routes: [
          GoRoute(path: 'new', builder: (_, _) => const CreateOrderScreen()),
        ],
      ),
      GoRoute(path: '/analytics', builder: (_, _) => const AnalyticsScreen()),
      GoRoute(path: '/admin', builder: (_, _) => const AdminScreen()),
      GoRoute(
        path: '/notifications',
        builder: (_, _) => const NotificationsScreen(),
      ),
    ],
  );
});
