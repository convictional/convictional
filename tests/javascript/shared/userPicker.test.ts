import { expect, test } from 'vitest';
import { userSearchFilterComponent, User } from '../../../app/javascript/shared/userPicker';

test('filterUsers', () => {
  const users: User[] = [
    { id: '1', name: 'Bob Beagle' },
    { id: '2', name: 'Ed Eagle' },
    { id: '3', name: 'Frankie Furter' },
    { id: '4', name: 'Eve Frankenstein' },
    { id: '5', name: 'Steven Universe' },
  ];

  const component = userSearchFilterComponent({ users });

  component.searchQuery = 'frank';
  component.filterUsers();
  expect(component.visibleUserIds).toEqual(['3', '4']);

  component.resetFilter();
  expect(component.searchQuery).toEqual('');
  expect(component.visibleUserIds).toEqual(['1', '2', '3', '4', '5']);

  component.searchQuery = 'Eagle';
  component.filterUsers();
  expect(component.visibleUserIds).toEqual(['1', '2']);

  component.resetFilter();
  expect(component.searchQuery).toEqual('');
  expect(component.visibleUserIds).toEqual(['1', '2', '3', '4', '5']);

  component.searchQuery = 'steve';
  component.filterUsers();
  expect(component.visibleUserIds).toEqual(['5']);

  component.resetFilter();
  expect(component.searchQuery).toEqual('');
  expect(component.visibleUserIds).toEqual(['1', '2', '3', '4', '5']);

  component.searchQuery = 'august';
  component.filterUsers();
  expect(component.visibleUserIds).toEqual([]);
});
