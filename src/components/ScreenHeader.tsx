import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { AdvancedToggle } from './AdvancedToggle';
import { SyncIndicator } from './SyncIndicator';
import { colors, spacing } from '../theme/colors';

interface Props {
  title: string;
  screen: string;
  showAdvancedToggle?: boolean;
}

export function ScreenHeader({ title, screen, showAdvancedToggle = true }: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.left}>
        <SyncIndicator />
        <Text style={styles.title}>{title}</Text>
      </View>
      {showAdvancedToggle && <AdvancedToggle screen={screen} />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  left: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { color: colors.text, fontSize: 20, fontWeight: '700' },
});
