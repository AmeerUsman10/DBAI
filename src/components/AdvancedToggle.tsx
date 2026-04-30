import React from 'react';
import { TouchableOpacity, Text, StyleSheet, View } from 'react-native';
import { useStore } from '../store/useStore';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';

export function AdvancedToggle({ screen }: { screen: string }) {
  const isAdvanced = useStore((s) => s.isAdvanced(screen));
  const toggle = useStore((s) => s.toggleAdvancedMode);

  return (
    <TouchableOpacity
      onPress={() => toggle(screen)}
      style={styles.button}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View style={[styles.pill, isAdvanced && styles.pillActive]}>
        <Text style={[styles.label, isAdvanced && styles.labelActive]}>
          {isAdvanced ? 'Advanced' : 'Simple'}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: { minHeight: minTapTarget, justifyContent: 'center' },
  pill: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.xl,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  pillActive: {
    borderColor: colors.primary,
    backgroundColor: colors.primaryDim,
  },
  label: { color: colors.textMuted, fontSize: 12, fontWeight: '600' },
  labelActive: { color: colors.text },
});
