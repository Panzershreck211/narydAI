import 'package:flutter/material.dart';

/// Палитра один в один с веб-панелью (web/src/styles.css, токены :root).
@immutable
class AppColors extends ThemeExtension<AppColors> {
  const AppColors({
    required this.bg,
    required this.surface,
    required this.surface2,
    required this.border,
    required this.text,
    required this.muted,
    required this.primary,
    required this.primaryInk,
    required this.primarySoft,
    required this.red,
    required this.redSoft,
    required this.amber,
    required this.amberSoft,
    required this.orange,
    required this.green,
    required this.greenSoft,
    required this.blue,
    required this.indigo,
    required this.grey,
  });

  final Color bg, surface, surface2, border, text, muted;
  final Color primary, primaryInk, primarySoft;
  final Color red,
      redSoft,
      amber,
      amberSoft,
      orange,
      green,
      greenSoft,
      blue,
      indigo,
      grey;

  static const dark = AppColors(
    bg: Color(0xFF0D141D),
    surface: Color(0xFF151F2B),
    surface2: Color(0xFF1A2634),
    border: Color(0xFF273444),
    text: Color(0xFFE6EDF5),
    muted: Color(0xFF93A1B3),
    primary: Color(0xFF4F9CF0),
    primaryInk: Color(0xFF06121F),
    primarySoft: Color(0xFF16304D),
    red: Color(0xFFEF5350),
    redSoft: Color(0xFF3A1A1C),
    amber: Color(0xFFF9A825),
    amberSoft: Color(0xFF3A3016),
    orange: Color(0xFFEF6C00),
    green: Color(0xFF66BB6A),
    greenSoft: Color(0xFF17311B),
    blue: Color(0xFF1E88E5),
    indigo: Color(0xFF7986CB),
    grey: Color(0xFF9AA4B2),
  );

  static const light = AppColors(
    bg: Color(0xFFF3F5F8),
    surface: Color(0xFFFFFFFF),
    surface2: Color(0xFFF8FAFC),
    border: Color(0xFFE2E7EE),
    text: Color(0xFF17202B),
    muted: Color(0xFF637083),
    primary: Color(0xFF1565C0),
    primaryInk: Color(0xFFFFFFFF),
    primarySoft: Color(0xFFE3EEFB),
    red: Color(0xFFD32F2F),
    redSoft: Color(0xFFFDECEC),
    amber: Color(0xFFF9A825),
    amberSoft: Color(0xFFFFF6DC),
    orange: Color(0xFFEF6C00),
    green: Color(0xFF2E7D32),
    greenSoft: Color(0xFFE7F4E8),
    blue: Color(0xFF1E88E5),
    indigo: Color(0xFF3949AB),
    grey: Color(0xFF9AA4B2),
  );

  @override
  AppColors copyWith() => this;

  @override
  AppColors lerp(AppColors? other, double t) =>
      t < 0.5 || other == null ? this : other;
}

extension AppColorsX on BuildContext {
  AppColors get colors => Theme.of(this).extension<AppColors>()!;
}

class AppTheme {
  AppTheme._();

  /// Как и панель, по умолчанию — тёмная тема (лучше читается в цеху и не слепит ночью).
  static const mode = ThemeMode.dark;

  static ThemeData light() => _build(Brightness.light, AppColors.light);
  static ThemeData dark() => _build(Brightness.dark, AppColors.dark);

  static ThemeData _build(Brightness brightness, AppColors c) {
    final scheme = ColorScheme(
      brightness: brightness,
      primary: c.primary,
      onPrimary: c.primaryInk,
      primaryContainer: c.primarySoft,
      onPrimaryContainer: c.text,
      secondary: c.primary,
      onSecondary: c.primaryInk,
      secondaryContainer: c.primarySoft,
      onSecondaryContainer: c.text,
      error: c.red,
      onError: Colors.white,
      surface: c.surface,
      onSurface: c.text,
      onSurfaceVariant: c.muted,
      surfaceContainerLowest: c.bg,
      surfaceContainerLow: c.surface,
      surfaceContainer: c.surface,
      surfaceContainerHigh: c.surface2,
      surfaceContainerHighest: c.surface2,
      outline: c.border,
      outlineVariant: c.border,
    );
    const r8 = BorderRadius.all(Radius.circular(8));
    const r10 = BorderRadius.all(Radius.circular(10));
    OutlineInputBorder inputBorder(Color color, [double width = 1]) =>
        OutlineInputBorder(
          borderRadius: r8,
          borderSide: BorderSide(color: color, width: width),
        );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      extensions: [c],
      scaffoldBackgroundColor: c.bg,
      canvasColor: c.bg,
      dividerColor: c.border,
      hintColor: c.muted,
      fontFamily: 'Roboto',
      materialTapTargetSize: MaterialTapTargetSize.padded,
      textTheme: Typography.material2021(platform: TargetPlatform.android)
          .englishLike
          .merge(
            brightness == Brightness.dark
                ? Typography.whiteMountainView
                : Typography.blackMountainView,
          )
          .apply(bodyColor: c.text, displayColor: c.text),
      appBarTheme: AppBarTheme(
        backgroundColor: c.surface,
        foregroundColor: c.text,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: c.text,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
        shape: Border(bottom: BorderSide(color: c.border)),
      ),
      cardTheme: CardThemeData(
        color: c.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        margin: const EdgeInsets.symmetric(vertical: 5),
        shape: RoundedRectangleBorder(
          borderRadius: r10,
          side: BorderSide(color: c.border),
        ),
      ),
      dividerTheme: DividerThemeData(color: c.border, space: 1),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: c.surface,
        isDense: true,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 14,
        ),
        labelStyle: TextStyle(color: c.muted),
        floatingLabelStyle: TextStyle(color: c.primary),
        hintStyle: TextStyle(color: c.muted),
        border: inputBorder(c.border),
        enabledBorder: inputBorder(c.border),
        focusedBorder: inputBorder(c.primary, 2),
        errorBorder: inputBorder(c.red),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: c.primary,
          foregroundColor: c.primaryInk,
          minimumSize: const Size(48, 48),
          shape: const RoundedRectangleBorder(borderRadius: r8),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: c.text,
          minimumSize: const Size(48, 48),
          side: BorderSide(color: c.border),
          shape: const RoundedRectangleBorder(borderRadius: r8),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w500),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: c.primary),
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
          shape: const WidgetStatePropertyAll(
            RoundedRectangleBorder(borderRadius: r8),
          ),
          side: WidgetStatePropertyAll(BorderSide(color: c.border)),
          backgroundColor: WidgetStateProperty.resolveWith(
            (s) => s.contains(WidgetState.selected) ? c.primary : c.surface,
          ),
          foregroundColor: WidgetStateProperty.resolveWith(
            (s) => s.contains(WidgetState.selected) ? c.primaryInk : c.text,
          ),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: c.surface,
        side: BorderSide(color: c.border),
        shape: const StadiumBorder(),
        labelStyle: TextStyle(color: c.text, fontSize: 13),
      ),
      tabBarTheme: TabBarThemeData(
        labelColor: c.text,
        unselectedLabelColor: c.muted,
        indicatorColor: c.primary,
        dividerColor: c.border,
        labelStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? c.primaryInk : c.muted,
        ),
        trackColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? c.primary : c.surface2,
        ),
        trackOutlineColor: WidgetStatePropertyAll(c.border),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: c.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: const BorderRadius.all(Radius.circular(14)),
          side: BorderSide(color: c.border),
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: c.surface,
        surfaceTintColor: Colors.transparent,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: c.surface2,
        contentTextStyle: TextStyle(color: c.text),
        shape: RoundedRectangleBorder(
          borderRadius: r10,
          side: BorderSide(color: c.border),
        ),
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(color: c.primary),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: c.primary,
        foregroundColor: c.primaryInk,
        shape: const RoundedRectangleBorder(borderRadius: r10),
      ),
      listTileTheme: ListTileThemeData(iconColor: c.muted, textColor: c.text),
      expansionTileTheme: ExpansionTileThemeData(
        iconColor: c.muted,
        collapsedIconColor: c.muted,
        textColor: c.text,
        collapsedTextColor: c.text,
        shape: const Border(),
        collapsedShape: const Border(),
      ),
    );
  }
}

/// Логотип как в панели: синий квадрат с «Н» + название.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.subtitle, this.big = false});

  final String? subtitle;
  final bool big;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final size = big ? 44.0 : 32.0;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: size,
          height: size,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: const Color(0xFF1565C0),
            borderRadius: BorderRadius.circular(big ? 10 : 8),
          ),
          child: Text(
            'Н',
            style: TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w800,
              fontSize: big ? 22 : 16,
            ),
          ),
        ),
        const SizedBox(width: 10),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'НарядAI',
              style: TextStyle(
                color: c.text,
                fontWeight: FontWeight.w700,
                fontSize: big ? 22 : 16,
              ),
            ),
            if (subtitle != null)
              Text(
                subtitle!,
                style: TextStyle(color: c.muted, fontSize: big ? 13 : 11),
              ),
          ],
        ),
      ],
    );
  }
}
