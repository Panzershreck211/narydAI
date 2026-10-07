import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_client.dart';
import '../../../core/i18n/i18n.dart';
import '../../../core/realtime/realtime_service.dart';
import '../../../core/widgets/common.dart';

final notificationsProvider =
    FutureProvider.autoDispose<List<Map<String, dynamic>>>((ref) async {
      ref.listen(realtimeEventsProvider, (_, next) {
        if (next.asData?.value is NotificationReceived) ref.invalidateSelf();
      });
      final res = await ref.watch(dioProvider).get('/notifications');
      return (res.data as List).cast<Map<String, dynamic>>();
    });

class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final dio = ref.read(dioProvider);
    return Scaffold(
      appBar: AppBar(
        title: Text(tr('Уведомления')),
        actions: [
          IconButton(
            tooltip: tr('Прочитать все'),
            icon: const Icon(Icons.done_all),
            onPressed: () async {
              await dio.post('/notifications/read-all');
              ref.invalidate(notificationsProvider);
            },
          ),
        ],
      ),
      body: AsyncView(
        value: ref.watch(notificationsProvider),
        onRetry: () => ref.invalidate(notificationsProvider),
        data: (items) => items.isEmpty
            ? Center(child: Text(tr('Уведомлений нет')))
            : ListView.separated(
                itemCount: items.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (_, i) {
                  final n = items[i];
                  final emergency = n['is_emergency'] == true;
                  return ListTile(
                    leading: Icon(
                      emergency
                          ? Icons.warning_amber_rounded
                          : Icons.notifications_none,
                      color: emergency ? Colors.red : null,
                    ),
                    title: Text(
                      n['title'],
                      style: TextStyle(
                        fontWeight: n['is_read'] == true
                            ? FontWeight.normal
                            : FontWeight.bold,
                      ),
                    ),
                    subtitle: Text(
                      '${n['body']}\n${dateTimeFmt.format(DateTime.parse(n['created_at']).toLocal())}',
                    ),
                    isThreeLine: true,
                    onTap: () async {
                      await dio.post('/notifications/${n['id']}/read');
                      ref.invalidate(notificationsProvider);
                      if (n['order_id'] != null && context.mounted) {
                        context.push('/orders/${n['order_id']}');
                      }
                    },
                  );
                },
              ),
      ),
    );
  }
}
