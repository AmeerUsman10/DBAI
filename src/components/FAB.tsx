import React from 'react';
import { TouchableOpacity, Text, StyleSheet } from 'react-native';
import { colors, radius } from '../theme/colors';

interface Props {
  label: string;
  onPress: () => void;
  bottom?: number;
}

export function FAB({ label, onPress, bottom = 24 }: Props) {
  return (
    <TouchableOpacity style={[styles.fab, { bottom }]} onPress={onPress} activeOpacity={0.85}>
      <Text style={styles.label}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  fab: {
    position: 'absolute',
    right: 20,
    backgroundColor: colors.primary,
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderRadius: radius.xl,
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.3,
    shadowRadius: 6,
    minWidth: 56,
    alignItems: 'center',
  },
  label: { color: '#000', fontWeight: '700', fontSize: 15 },
});
