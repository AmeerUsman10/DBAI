import React from 'react';
import { View, StyleSheet } from 'react-native';
import { useStore } from '../store/useStore';
import { colors } from '../theme/colors';

export function SyncIndicator() {
  const syncStatus = useStore((s) => s.syncStatus);

  const dotColor =
    syncStatus === 'synced' ? colors.syncGreen
    : syncStatus === 'pending' ? colors.syncAmber
    : colors.textDim;

  return <View style={[styles.dot, { backgroundColor: dotColor }]} />;
}

const styles = StyleSheet.create({
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 4,
  },
});
