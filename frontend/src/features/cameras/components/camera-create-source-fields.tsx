import { Add01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import { HugeiconsIcon } from "@hugeicons/react";
import type {
  FieldArrayWithId,
  FieldErrors,
  UseFormRegister,
} from "react-hook-form";

import { Button } from "@/components/ui/button";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
  FieldLegend,
  FieldSet,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { fieldErrorMessage } from "@/features/cameras/forms/camera-create-error-mapping";
import type { CameraCreateFormValues } from "@/features/cameras/forms/camera-create-form";

type CameraSourceField = FieldArrayWithId<
  CameraCreateFormValues,
  "sources",
  "id"
>;

interface CameraCreateSourceFieldsProps {
  readonly formId: string;
  readonly fields: readonly CameraSourceField[];
  readonly sources: CameraCreateFormValues["sources"];
  readonly register: UseFormRegister<CameraCreateFormValues>;
  readonly errors: FieldErrors<CameraCreateFormValues>;
  readonly defaultSourceFieldId: string | undefined;
  readonly disabled: boolean;
  readonly onAddSource: () => void;
  readonly onRemoveSource: (index: number) => void;
  readonly onDefaultSourceChange: (fieldId: string) => void;
}

/**
 * Source 编辑器只呈现父 Dialog 已拥有的 Field Array。
 *
 * 新增 Source 只会追加到列表末尾，删除后保留其余 Source 的相对顺序。界面不提供排序能力，
 * 因此用户看到的添加顺序就是最终提交顺序。
 */
export function CameraCreateSourceFields({
  formId,
  fields,
  sources,
  register,
  errors,
  defaultSourceFieldId,
  disabled,
  onAddSource,
  onRemoveSource,
  onDefaultSourceChange,
}: CameraCreateSourceFieldsProps) {
  const sourceRootError = fieldErrorMessage(errors.sources?.message);

  return (
    <FieldSet
      className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1"
      disabled={disabled}
    >
      <FieldLegend className="mb-0">视频源</FieldLegend>
      <FieldDescription className="col-start-1 row-start-2">
        选择一路作为默认预览源。
      </FieldDescription>
      <Button
        className="col-start-2 row-span-2 row-start-1 self-start"
        type="button"
        variant="outline"
        onClick={onAddSource}
        disabled={disabled}
      >
        <HugeiconsIcon
          icon={Add01Icon}
          strokeWidth={2}
          data-icon="inline-start"
        />
        添加视频源
      </Button>
      {sourceRootError === undefined ? null : (
        <FieldError className="col-span-2 mt-2">{sourceRootError}</FieldError>
      )}

      <RadioGroup
        className="col-span-2 mt-2 gap-2"
        value={defaultSourceFieldId}
        onValueChange={onDefaultSourceChange}
        disabled={disabled}
        aria-label="默认预览源"
      >
        {fields.map((sourceField, index) => {
          const sourceErrors = errors.sources?.[index];
          const defaultError = fieldErrorMessage(
            sourceErrors?.is_default_preview?.message,
          );

          return (
            <FieldSet
              key={sourceField.id}
              className="grid min-w-0 grid-cols-[1.25rem_minmax(0,1fr)_2rem] items-start gap-2 sm:grid-cols-[1.25rem_minmax(9rem,0.7fr)_minmax(12rem,1.3fr)_2rem]"
              data-testid="camera-source-editor"
            >
              <FieldLegend className="sr-only">
                视频源 {index + 1} 配置
              </FieldLegend>
              <RadioGroupItem
                className="col-start-1 row-start-1 mt-2"
                id={`${formId}-default-${sourceField.id}`}
                value={sourceField.id}
                aria-label={`设视频源 ${index + 1} 为默认预览源${
                  sources[index]?.is_default_preview ? "（当前默认）" : ""
                }`}
                aria-invalid={defaultError !== undefined}
                data-camera-create-field={`sources.${index}.is_default_preview`}
              />
              <input
                type="hidden"
                {...register(`sources.${index}.is_default_preview`)}
              />

              <Field
                className="col-start-2 row-start-1 min-w-0"
                data-invalid={sourceErrors?.name !== undefined}
                data-disabled={disabled}
              >
                <FieldLabel
                  className="sr-only"
                  htmlFor={`${formId}-source-${sourceField.id}-name`}
                >
                  名称
                </FieldLabel>
                <Input
                  id={`${formId}-source-${sourceField.id}-name`}
                  placeholder="例如：通道 1 主码流"
                  autoComplete="off"
                  aria-invalid={sourceErrors?.name !== undefined}
                  data-camera-create-field={`sources.${index}.name`}
                  {...register(`sources.${index}.name`)}
                />
                <FieldError>
                  {fieldErrorMessage(sourceErrors?.name?.message)}
                </FieldError>
              </Field>

              <Field
                className="col-start-2 row-start-2 min-w-0 sm:col-start-3 sm:row-start-1"
                data-invalid={sourceErrors?.url_suffix !== undefined}
                data-disabled={disabled}
              >
                <FieldLabel
                  className="sr-only"
                  htmlFor={`${formId}-source-${sourceField.id}-suffix`}
                >
                  URL 后缀
                </FieldLabel>
                <Input
                  id={`${formId}-source-${sourceField.id}-suffix`}
                  placeholder="例如：Stream/Channels/101"
                  autoComplete="off"
                  aria-invalid={sourceErrors?.url_suffix !== undefined}
                  data-camera-create-field={`sources.${index}.url_suffix`}
                  {...register(`sources.${index}.url_suffix`)}
                />
                <FieldError>
                  {fieldErrorMessage(sourceErrors?.url_suffix?.message)}
                </FieldError>
              </Field>

              <Button
                className="col-start-3 row-span-2 row-start-1 sm:col-start-4 sm:row-span-1"
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label={`删除视频源 ${index + 1}`}
                disabled={disabled || fields.length === 1}
                onClick={() => onRemoveSource(index)}
              >
                <HugeiconsIcon
                  icon={Delete02Icon}
                  strokeWidth={2}
                  data-icon="inline-start"
                />
              </Button>
              {defaultError === undefined ? null : (
                <FieldError className="col-span-full">
                  {defaultError}
                </FieldError>
              )}
            </FieldSet>
          );
        })}
      </RadioGroup>
    </FieldSet>
  );
}
