import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/realtime/realtime_service.dart';
import '../data/orders_repository.dart';
import '../domain/work_order.dart';

/// Перезапрашивает провайдер при событии по WebSocket — обновление в реальном времени.
void _refreshOnRealtime(Ref ref, {int? orderId}) {
  ref.listen(realtimeEventsProvider, (_, next) {
    final event = next.asData?.value;
    if (event is OrderChanged &&
        (orderId == null || event.orderId == orderId)) {
      ref.invalidateSelf();
    }
  });
}

/// Наряды текущего пользователя (исполнитель видит только свои — фильтр на бэкенде).
final myOrdersProvider = FutureProvider.autoDispose<List<WorkOrder>>((ref) {
  _refreshOnRealtime(ref);
  return ref.watch(ordersRepositoryProvider).list();
});

final orderDetailProvider = FutureProvider.autoDispose.family<OrderDetail, int>(
  (ref, id) {
    _refreshOnRealtime(ref, orderId: id);
    return ref.watch(ordersRepositoryProvider).get(id);
  },
);
