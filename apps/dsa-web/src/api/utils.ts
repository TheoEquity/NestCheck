import camelcaseKeys from 'camelcase-keys';
import snakecaseKeys from 'snakecase-keys';

/**
 * 将 snake_case 对象键转换为 camelCase
 * @param data API 响应数据 (snake_case)
 * @returns 转换后的 camelCase 对象
 */
export function toCamelCase<T>(data: unknown): T {
    if (data === null || data === undefined) {
        return data as T;
    }
    return camelcaseKeys(data as Record<string, unknown>, { deep: true }) as T;
}

/**
 * 将 camelCase 对象键转换为 snake_case
 * @param data 前端数据 (camelCase)
 * @returns 转换后的 snake_case 对象
 */
export function toSnakeCase<T>(data: unknown): T {
    if (data === null || data === undefined) {
        return data as T;
    }
    return snakecaseKeys(data as Record<string, unknown>, { deep: true }) as T;
}
