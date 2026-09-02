import {
  Add01Icon,
  ArrowDown02Icon,
  ArrowUp02Icon,
  Delete02Icon,
} from "@hugeicons/core-free-icons";
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
import type { CameraEditFormValues } from "@/features/cameras/forms/camera-edit-form";
import { fieldErrorMessage } from "@/features/cameras/forms/camera-form-errors";

type CameraEditSourceField = FieldArrayWithId<
  CameraEditFormValues,
  "sources",
  "id"
>;

interface CameraEditSourceFieldsProps {
  readonly formId: string;
  readonly fields: readonly CameraEditSourceField[];
  readonly sources: CameraEditFormValues["sources"];
  readonly register: UseFormRegister<CameraEditFormValues>;
  readonly errors: FieldErrors<CameraEditFormValues>;
  readonly defaultSourceFieldId: string | undefined;
  readonly disabled: boolean;
  readonly onAddSource: () => void;
  readonly onRemoveSource: (index: number) => void;
  readonly onMoveSource: (from: number, to: number) => void;
  readonly onDefaultSourceChange: (fieldId: string) => void;
}

/** 完整编辑使用稳定 Backend ID，排序按钮只移动 Field Array 行，不重建 Source 身份。 */
export function CameraEditSourceFields({
  formId,
  fields,
  sources,
  register,
  errors,
  defaultSourceFieldId,
  disabled,
  onAddSource,
  onRemoveSource,
  onMoveSource,
  onDefaultSourceChange,
}: CameraEditSourceFieldsProps) {
  const sourceRootError = fieldErrorMessage(errors.sources?.message);

  return (
    <FieldSet
      className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1"
      disabled={disabled}
    >
      <FieldLegend className="mb-0">视频源</FieldLegend>
      <FieldDescription className="col-start-1 row-start-2">
        选择默认预览源，并使用按钮调整保存顺序。
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
          const sourceIdError = fieldErrorMessage(
            sourceErrors?.source_id?.message,
          );

          return (
            <FieldSet
              key={sourceField.id}
              className="grid min-w-0 grid-cols-[1.25rem_minmax(0,1fr)_auto] items-start gap-2 sm:grid-cols-[1.25rem_minmax(9rem,0.7fr)_minmax(12rem,1.3fr)_auto]"
              data-testid="camera-edit-source-editor"
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
                data-camera-edit-field={`sources.${index}.is_default_preview`}
              />
              <input
                type="hidden"
                {...register(`sources.${index}.is_default_preview`)}
              />
              {sourceField.source_id === undefined ? null : (
                <input
                  type="hidden"
                  {...register(`sources.${index}.source_id`)}
                />
              )}

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
                  disabled={disabled}
                  aria-invalid={sourceErrors?.name !== undefined}
                  data-camera-edit-field={`sources.${index}.name`}
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
                  disabled={disabled}
                  aria-invalid={sourceErrors?.url_suffix !== undefined}
                  data-camera-edit-field={`sources.${index}.url_suffix`}
                  {...register(`sources.${index}.url_suffix`)}
                />
                <FieldError>
                  {fieldErrorMessage(sourceErrors?.url_suffix?.message)}
                </FieldError>
              </Field>

              <div className="col-start-3 row-span-2 row-start-1 flex gap-1 sm:col-start-4 sm:row-span-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`上移视频源 ${index + 1}`}
                  disabled={disabled || index === 0}
                  onClick={() => onMoveSource(index, index - 1)}
                >
                  <HugeiconsIcon
                    icon={ArrowUp02Icon}
                    strokeWidth={2}
                    data-icon="inline-start"
                  />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`下移视频源 ${index + 1}`}
                  disabled={disabled || index === fields.length - 1}
                  onClick={() => onMoveSource(index, index + 1)}
                >
                  <HugeiconsIcon
                    icon={ArrowDown02Icon}
                    strokeWidth={2}
                    data-icon="inline-start"
                  />
                </Button>
                <Button
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
              </div>
              {defaultError === undefined ? null : (
                <FieldError className="col-span-full">
                  {defaultError}
                </FieldError>
              )}
              {sourceIdError === undefined ? null : (
                <FieldError className="col-span-full">
                  {sourceIdError}
                </FieldError>
              )}
            </FieldSet>
          );
        })}
      </RadioGroup>
    </FieldSet>
  );
}
